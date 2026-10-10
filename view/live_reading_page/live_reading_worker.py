"""Background read-only feedback acquisition; no database dependency."""
import math
import time
from datetime import datetime, timezone
from threading import Event, Lock
from PySide6.QtCore import QThread, Signal


class LiveReadingWorker(QThread):
    failed = Signal(str)

    def __init__(self, config, parent=None):
        if config is None:
            raise ValueError("Robot configuration is required")
        super().__init__(parent)
        self.config = config
        self._stop = Event()
        self._lock = Lock()
        self._latest = None

    def request_stop(self):
        self._stop.set()

    def latest(self):
        # The GUI polls a locked snapshot instead of queuing every feedback signal.
        with self._lock:
            return self._latest

    def publish(self, joints, base):
        if len(joints) != 6 or any(not math.isfinite(v) for j in joints for v in j.values()):
            raise ValueError("Invalid feedback for six joints")
        with self._lock:
            self._latest = dict(time=datetime.now(timezone.utc), joints=joints, base=base)

    def run(self):
        transport = session = options = None
        connected = False
        transport_connected = False
        try:
            from kortex_api.UDPTransport import UDPTransport
            from kortex_api.RouterClient import RouterClient, RouterClientSendOptions
            from kortex_api.SessionManager import SessionManager
            from kortex_api.autogen.messages import Session_pb2
            from kortex_api.autogen.client_stubs.BaseCyclicClientRpc import BaseCyclicClient
            transport = UDPTransport()
            router = RouterClient(transport)
            transport.connect(self.config["host"], self.config["port"])
            transport_connected = True
            options = RouterClientSendOptions()
            options.timeout_ms = 2000
            session = SessionManager(router)
            credentials = Session_pb2.CreateSessionInfo()
            credentials.username = self.config["username"]
            credentials.password = self.config["password"]
            credentials.session_inactivity_timeout = 60000
            credentials.connection_inactivity_timeout = 2000
            session.CreateSession(credentials, options=options)
            connected = True
            cyclic = BaseCyclicClient(router)
            while not self._stop.is_set():
                started = time.monotonic()
                feedback = cyclic.RefreshFeedback(options=options)
                joints = [dict(position=a.position, velocity=a.velocity, torque=a.torque,
                               current=a.current_motor, temperature=a.temperature_motor)
                          for a in feedback.actuators]
                base = {key: getattr(feedback.base, key) for key in (
                    "arm_voltage", "arm_current", "temperature_cpu", "temperature_ambient",
                    "tool_pose_x", "tool_pose_y", "tool_pose_z", "tool_pose_theta_x",
                    "tool_pose_theta_y", "tool_pose_theta_z")}
                self.publish(joints, base)
                self._stop.wait(max(0, .1 - (time.monotonic() - started)))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            if connected:
                try:
                    session.CloseSession(options=options)
                except Exception as error:
                    self.failed.emit(f"Session shutdown: {error}")
            if transport_connected:
                try:
                    transport.disconnect()
                except Exception as error:
                    self.failed.emit(f"Transport shutdown: {error}")
