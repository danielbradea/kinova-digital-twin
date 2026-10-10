import psycopg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget

from .widgets import add_field, card, connection_status, input_field, update_connection_status

class ConnectionsComponent(QWidget):
    """Robot/database connection fields, statuses and test action."""
    connections_changed = Signal(bool, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_connected = False
        self.robot_connected = False
        connections = QVBoxLayout(self)
        connections.setContentsMargins(0, 0, 0, 0)
        connections.setSpacing(16)
        self.connections_grid = QGridLayout()
        self.connections_grid.setSpacing(20)
        connections.addLayout(self.connections_grid)

        self.robot_status = connection_status()
        self.robot_card, robot = card("Robot connection", self.robot_status)
        self.robot_ip_input = input_field("192.168.1.10", default_value="192.168.1.10")
        self.robot_username_input = input_field("admin", default_value="admin")
        self.robot_password_input = input_field("Password", password=True, default_value="admin")
        self.robot_port_input = input_field("10001", default_value="10001")
        for label, field in (
            ("IP Address", self.robot_ip_input),
            ("Username", self.robot_username_input),
            ("Password", self.robot_password_input),
            ("UDP Port", self.robot_port_input),
        ):
            add_field(robot, label, field)
        robot.addStretch()

        self.db_status = connection_status()
        self.db_card, database = card("Database connection", self.db_status)
        self.db_host_input = input_field("localhost", default_value="localhost")
        self.db_port_input = input_field("5432", default_value="5432")
        self.db_name_input = input_field("kinova", default_value="kinova")
        self.db_user_input = input_field("kinova", default_value="kinova")
        self.db_password_input = input_field("kinova", password=True, default_value="kinova123#")
        for label, field in (
            ("Host", self.db_host_input), ("Port", self.db_port_input),
            ("Database", self.db_name_input), ("User", self.db_user_input),
            ("Password", self.db_password_input),
        ):
            add_field(database, label, field)
        database.addStretch()

        self.test_connections_button = QPushButton("Test Connections")
        self.test_connections_button.setMinimumHeight(40)
        self.test_connections_button.clicked.connect(self.check_connections)
        connections.addWidget(self.test_connections_button)

        self.set_compact(False)
        for field in (
            self.robot_ip_input, self.robot_username_input,
            self.robot_password_input, self.robot_port_input,
        ):
            field.textChanged.connect(lambda _text: self._invalidate_connection("robot"))
        for field in (
            self.db_host_input, self.db_port_input, self.db_name_input,
            self.db_user_input, self.db_password_input,
        ):
            field.textChanged.connect(lambda _text: self._invalidate_connection("db"))

    def _set_connection_result(self, service, connected):
        setattr(self, f"{service}_connected", connected)
        self.connections_changed.emit(self.db_connected, self.robot_connected)

    def _invalidate_connection(self, service):
        self._set_connection_result(service, False)
        label = getattr(self, f"{service}_status")
        update_connection_status(label, "disconnected")
        label.setToolTip("")

    def set_compact(self, compact):
        """Stack the connection cards when the page has limited width."""
        grid = self.connections_grid
        while grid.count():
            grid.takeAt(0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0 if compact else 1)
        grid.addWidget(self.robot_card, 0, 0)
        grid.addWidget(self.db_card, 1 if compact else 0, 0 if compact else 1)

    def check_connections(self):
        """Test both services independently and always restore the button."""
        self.test_connections_button.setDisabled(True)
        self.test_connections_button.repaint()
        try:
            self._set_connection_result("db", False)
            self._set_connection_result("robot", False)
            self.check_db_connection()
            self.check_robot_connection()
        finally:
            self.test_connections_button.setDisabled(False)

    def check_db_connection(self):
        self._set_connection_result("db", False)
        update_connection_status(self.db_status, "connecting")
        self.db_status.setToolTip("")
        self.db_status.repaint()
        try:
            with psycopg.connect(
                host=self.db_host_input.text().strip(),
                port=self.db_port_input.text().strip(),
                dbname=self.db_name_input.text().strip(),
                user=self.db_user_input.text().strip(),
                password=self.db_password_input.text(),
                connect_timeout=5,
            ) as connection:
                result = connection.execute("SELECT 1").fetchone()
                if result != (1,):
                    raise RuntimeError("Unexpected response to SELECT 1")
            print("Database connection OK:", result)
            update_connection_status(self.db_status, "connected")
            self._set_connection_result("db", True)
            return True
        except Exception as error:
            print("Database connection failed:", error)
            update_connection_status(self.db_status, "failed")
            self.db_status.setToolTip(str(error))
            return False

    def check_robot_connection(self):
        """Authenticate over UDP and read the same feedback used for recording."""
        self._set_connection_result("robot", False)
        update_connection_status(self.robot_status, "connecting")
        self.robot_status.setToolTip("")
        self.robot_status.repaint()
        transport = None
        session = None
        session_created = False
        transport_connected = False
        try:
            # Import here so an incompatible SDK does not prevent DB testing.
            try:
                from kortex_api.UDPTransport import UDPTransport
                from kortex_api.RouterClient import RouterClient, RouterClientSendOptions
                from kortex_api.SessionManager import SessionManager
                from kortex_api.autogen.messages import Session_pb2
                from kortex_api.autogen.client_stubs.BaseCyclicClientRpc import BaseCyclicClient
            except ImportError as error:
                raise RuntimeError(
                    "Incompatible Kortex SDK: the Gen3 SDK is required "
                    "with UDPTransport and BaseCyclicClient (port 10001)."
                ) from error

            port = int(self.robot_port_input.text().strip())
            if not 1 <= port <= 65535:
                raise ValueError("Robot port must be between 1 and 65535")
            transport = UDPTransport()
            router = RouterClient(transport)
            transport.connect(self.robot_ip_input.text().strip(), port)
            transport_connected = True
            options = RouterClientSendOptions()
            options.timeout_ms = 5000
            session = SessionManager(router)
            credentials = Session_pb2.CreateSessionInfo()
            credentials.username = self.robot_username_input.text().strip()
            credentials.password = self.robot_password_input.text()
            credentials.session_inactivity_timeout = 10000
            credentials.connection_inactivity_timeout = 2000
            session.CreateSession(credentials, options=options)
            session_created = True
            feedback = BaseCyclicClient(router).RefreshFeedback(options=options)
            if len(feedback.actuators) < 6:
                raise RuntimeError("The robot returned fewer than 6 actuators")
            print("Kinova connection OK")
            update_connection_status(self.robot_status, "connected")
            self._set_connection_result("robot", True)
            return True
        except Exception as error:
            print("Kinova connection failed:", error)
            update_connection_status(self.robot_status, "failed")
            self.robot_status.setToolTip(str(error))
            return False
        finally:
            try:
                if session_created:
                    session.CloseSession(options=options)
            except Exception as error:
                print("Kinova session shutdown error:", error)
            finally:
                if transport_connected:
                    try:
                        transport.disconnect()
                    except Exception as error:
                        print("Kinova transport shutdown error:", error)
