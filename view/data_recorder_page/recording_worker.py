"""Background acquisition of Kinova feedback and PostgreSQL batch writes."""
import time
from datetime import datetime, timezone
from threading import Event

import psycopg
from psycopg import sql
from PySide6.QtCore import QThread, Signal


COLUMNS = [
    "time",
    *[f"joint_{i}_{field}" for i in range(1, 7)
      for field in ("position", "velocity", "torque", "current", "temperature")],
    "arm_voltage", "arm_current", "temperature_cpu", "temperature_ambient",
    "tool_x", "tool_y", "tool_z", "tool_theta_x", "tool_theta_y", "tool_theta_z",
]


def build_insert_sql(table):
    parts = table.strip().split(".")
    if len(parts) not in (1, 2) or any(not part for part in parts):
        raise ValueError("Enter table or schema.table")
    return sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(*parts),
        sql.SQL(", ").join(sql.Identifier(name) for name in COLUMNS),
        sql.SQL(", ").join(sql.Placeholder() for _ in COLUMNS),
    )


class RecordingWorker(QThread):
    recording_started = Signal()
    samples_saved = Signal(int)
    failed = Signal(str)

    def __init__(self, config, insert_sql, parent=None):
        super().__init__(parent)
        self.config = config
        self.insert_sql = insert_sql
        self._stop = Event()

    def request_stop(self):
        self._stop.set()

    @staticmethod
    def feedback_row(feedback):
        if len(feedback.actuators) < 6:
            raise RuntimeError("The robot returned fewer than 6 actuators")
        row = [datetime.now(timezone.utc)]
        for actuator in feedback.actuators[:6]:
            row.extend((actuator.position, actuator.velocity, actuator.torque,
                        actuator.current_motor, actuator.temperature_motor))
        base = feedback.base
        row.extend(getattr(base, name) for name in (
            "arm_voltage", "arm_current", "temperature_cpu", "temperature_ambient",
            "tool_pose_x", "tool_pose_y", "tool_pose_z", "tool_pose_theta_x",
            "tool_pose_theta_y", "tool_pose_theta_z",
        ))
        return tuple(row)

    def run(self):
        transport = session = connection = cursor = None
        session_created = False
        transport_connected = False
        buffer = []
        saved = 0
        errors = []
        options = None

        def flush():
            # Update the counter only after PostgreSQL commits the complete batch.
            nonlocal saved
            if not buffer:
                return
            cursor.executemany(self.insert_sql, buffer)
            connection.commit()
            saved += len(buffer)
            buffer.clear()
            self.samples_saved.emit(saved)

        try:
            from kortex_api.UDPTransport import UDPTransport
            from kortex_api.RouterClient import RouterClient, RouterClientSendOptions
            from kortex_api.SessionManager import SessionManager
            from kortex_api.autogen.client_stubs.BaseCyclicClientRpc import BaseCyclicClient
            from kortex_api.autogen.messages import Session_pb2

            connection = psycopg.connect(**self.config["database"], connect_timeout=5,
                                         options="-c statement_timeout=5000")
            cursor = connection.cursor()
            if self._stop.is_set():
                return
            transport = UDPTransport()
            router = RouterClient(transport)
            transport.connect(self.config["robot"]["host"], self.config["robot"]["port"])
            transport_connected = True
            options = RouterClientSendOptions()
            options.timeout_ms = 5000
            credentials = Session_pb2.CreateSessionInfo()
            credentials.username = self.config["robot"]["username"]
            credentials.password = self.config["robot"]["password"]
            credentials.session_inactivity_timeout = 60000
            credentials.connection_inactivity_timeout = 2000
            session = SessionManager(router)
            session.CreateSession(credentials, options=options)
            session_created = True
            cyclic = BaseCyclicClient(router)
            if not self._stop.is_set():
                self.recording_started.emit()
            while not self._stop.is_set():
                started = time.monotonic()
                feedback = cyclic.RefreshFeedback(options=options)
                buffer.append(self.feedback_row(feedback))
                if len(buffer) >= 100:
                    flush()
                self._stop.wait(max(0, self.config["interval"] - (time.monotonic() - started)))
        except Exception as error:
            errors.append(str(error))
        finally:
            if buffer and connection is not None and cursor is not None:
                try:
                    connection.rollback()
                    flush()
                except Exception as error:
                    errors.append(f"The final buffer could not be saved: {error}")
            for resource in (cursor, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception as error:
                        errors.append(f"PostgreSQL shutdown: {error}")
            if session_created:
                try:
                    session.CloseSession(options=options)
                except Exception as error:
                    errors.append(f"Session shutdown Kinova: {error}")
            if transport_connected:
                try:
                    transport.disconnect()
                except Exception as error:
                    errors.append(f"Transport shutdown Kinova: {error}")
            if errors:
                self.failed.emit("\n".join(errors))
