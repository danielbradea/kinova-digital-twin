
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
from PySide6.QtWidgets import QLineEdit, QAbstractSpinBox, QComboBox, QMessageBox

from view.charts_view_page.charts_view_page import ChartsViewPage
from view.charts_view_page.selected_charts_view_page import SelectedChartsViewPage
from view.kinova_view_page import KinovaViewPage
from view.data_table_page import DataTablePage
from view.live_reading_page import LiveReadingPage
from view.data_recorder_page import DataRecorderPage
from view.home_page import HomePage

class AppLayout(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("KDT-App")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #f3f5f9;
                color: #243247;
            }
            QLabel { background-color: transparent; }
            QPushButton {
                background-color: white;
                border: 1px solid #cfd7e3;
                border-radius: 7px;
                color: #334155;
            }
            QPushButton:hover { background-color: #edf2fa; }
        """)

        # =====================================================
        # CENTRAL WIDGET
        # =====================================================

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # =====================================================
        # HEADER
        # =====================================================

        header = QWidget()
        header_layout = QHBoxLayout(header)

        self.menu_button = QPushButton("☰")
        self.menu_button.setFixedWidth(50)
        self.menu_button.clicked.connect(self.toggle_menu)

        title = QLabel("KINOVA DIGITAL TWIN")

        header_layout.addWidget(self.menu_button)
        header_layout.addWidget(title)
        header_layout.addStretch()

        main_layout.addWidget(header)

        # =====================================================
        # MAIN AREA
        # =====================================================

        body = QWidget()
        body_layout = QHBoxLayout(body)

        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        main_layout.addWidget(body, 1)

        # =====================================================
        # DRAWER / SIDEBAR
        # =====================================================

        self.drawer = QWidget()
        self.drawer.setFixedWidth(120)
        self.drawer.setVisible(False)

        drawer_layout = QVBoxLayout(self.drawer)

        btn_home = QPushButton("Home")
        btn_data_record = QPushButton("Data Recorder")
        btn_live_reading = QPushButton("Live Reading")
        btn_data_table = QPushButton("Data Table")
        btn_kinova_view_page = QPushButton("Kinova Digital Twin")
        btn_chats_view_page = QPushButton("Live charts")

        drawer_layout.addWidget(btn_home)
        drawer_layout.addWidget(btn_data_record)
        drawer_layout.addWidget(btn_live_reading)
        drawer_layout.addWidget(btn_data_table)
        drawer_layout.addWidget(btn_kinova_view_page)
        drawer_layout.addWidget(btn_chats_view_page)

        drawer_layout.addStretch()

        body_layout.addWidget(self.drawer)

        # =====================================================
        # CONTENT
        # =====================================================

        self.content = QStackedWidget()

        # PAGES
        home_page = HomePage()
        data_recorder_page = DataRecorderPage()
        live_reading_page = LiveReadingPage(self.live_robot_config)
        data_table_page = DataTablePage(self.table_database_config)
        kinova_view_page = KinovaViewPage(self.table_database_config)
        chats_view_page = ChartsViewPage(self.live_robot_config)
        self.charts_view_page = chats_view_page
        self.selected_charts_view_page = SelectedChartsViewPage()
        self.selected_charts_view_page.back_requested.connect(
            lambda: self.content.setCurrentWidget(self.data_table_page))
        data_table_page.charts_requested.connect(self.show_selected_charts)

        self.kinova_view_page = kinova_view_page
        data_table_page.replay_requested.connect(self.show_selected_in_kinova)

        self.data_table_page = data_table_page

        self.live_reading_page = live_reading_page

        self.data_recorder_page = data_recorder_page
        self._waiting_for_recording = False
        self._close_recording_confirmed = False
        self._close_confirmation_open = False

        # Add pages
        self.content.addWidget(home_page)
        self.content.addWidget(data_recorder_page)
        self.content.addWidget(live_reading_page)
        self.content.addWidget(data_table_page)
        self.content.addWidget(kinova_view_page)
        self.content.addWidget(chats_view_page)
        self.content.addWidget(self.selected_charts_view_page)

        body_layout.addWidget(self.content, 1)

        # =====================================================
        # NAVIGATION
        # =====================================================

        btn_home.clicked.connect(
            lambda: self.content.setCurrentWidget(home_page)
        )

        btn_data_record.clicked.connect(
            lambda: self.content.setCurrentWidget(data_recorder_page)
        )

        btn_live_reading.clicked.connect(
            lambda: self.content.setCurrentWidget(live_reading_page)
        )

        btn_data_table.clicked.connect(
            lambda: self.content.setCurrentWidget(data_table_page)
        )

        btn_kinova_view_page.clicked.connect(
            self.open_kinova_latest
        )

        btn_chats_view_page.clicked.connect(
            lambda: self.content.setCurrentWidget(chats_view_page)
        )

        self.align_input_heights()

        # =========================================================
        # OPEN / CLOSE DRAWER
        # =========================================================

    def align_input_heights(self):
        """Match all form controls to the styled Data Table button height."""
        reference = self.data_table_page.search_button
        reference.ensurePolished()
        height = reference.sizeHint().height()
        for button in self.data_table_page.action_buttons:
            button.setFixedHeight(height)
        for control in self.findChildren(QWidget):
            if isinstance(control, (QAbstractSpinBox, QComboBox)):
                control.setFixedHeight(height)
            elif isinstance(control, QLineEdit):
                # Spin boxes and editable combos size their own internal editor.
                if not isinstance(control.parentWidget(), (QAbstractSpinBox, QComboBox)):
                    control.setFixedHeight(height)

    def open_kinova_latest(self):
        self.kinova_view_page.load_latest()
        self.content.setCurrentWidget(self.kinova_view_page)

    def show_selected_charts(self, rows):
        if self.selected_charts_view_page.set_selected_rows(rows):
            self.content.setCurrentWidget(self.selected_charts_view_page)

    def show_selected_in_kinova(self, rows):
        if self.kinova_view_page.set_selected_rows(rows):
            self.content.setCurrentWidget(self.kinova_view_page)

    def toggle_menu(self):
        self.drawer.setVisible(
            not self.drawer.isVisible()
        )

    def live_robot_config(self):
        connection = self.data_recorder_page.connections_component
        port = int(connection.robot_port_input.text().strip())
        host = connection.robot_ip_input.text().strip()
        if not host or not 1 <= port <= 65535:
            raise ValueError("Check the robot IP address and port in Data Recorder")
        return dict(host=host, port=port,
                    username=connection.robot_username_input.text().strip(),
                    password=connection.robot_password_input.text())

    def table_database_config(self):
        connection = self.data_recorder_page.connections_component
        return {"database": {
            "host": connection.db_host_input.text().strip(),
            "port": connection.db_port_input.text().strip(),
            "dbname": connection.db_name_input.text().strip(),
            "user": connection.db_user_input.text().strip(),
            "password": connection.db_password_input.text(),
        }, "table": self.data_recorder_page.recording_component.table_input.text().strip()}

    def closeEvent(self, event):
        if self._close_confirmation_open:
            event.ignore()
            return
        recording_worker = self.data_recorder_page.recording_worker
        if recording_worker is not None and not self._close_recording_confirmed:
            # Ask before stopping any stream; cancelling leaves recording running.
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Recording in progress")
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setText("Data is currently being recorded to the database.")
            dialog.setInformativeText(
                "Closing the application will stop recording. "
                "The application will wait for the remaining data to be saved before closing.")
            stop_close = dialog.addButton(
                "Stop recording and close", QMessageBox.ButtonRole.AcceptRole)
            cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(cancel)
            dialog.setEscapeButton(cancel)
            self._close_confirmation_open = True
            try:
                dialog.exec()
            finally:
                self._close_confirmation_open = False
            if dialog.clickedButton() is not stop_close:
                event.ignore()
                return
            self._close_recording_confirmed = True
        # Defer closing until workers release sockets and database connections.
        self.charts_view_page.stop_stream()
        charts_worker = self.charts_view_page.worker
        if charts_worker is not None and charts_worker.isRunning():
            if not getattr(self, "_waiting_for_charts", False):
                self._waiting_for_charts = True
                charts_worker.finished.connect(self.close)
            self.kinova_view_page.pause()
            self.live_reading_page.stop_stream()
            self.data_recorder_page.recording_component.stop_recording()
            event.ignore()
            return
        self.kinova_view_page.pause()
        twin_worker = self.kinova_view_page.worker
        if twin_worker is not None and twin_worker.isRunning():
            if not getattr(self, "_waiting_for_twin", False):
                self._waiting_for_twin = True
                twin_worker.finished.connect(self.close)
            self.live_reading_page.stop_stream()
            self.data_recorder_page.recording_component.stop_recording()
            event.ignore()
            return
        query_worker = self.data_table_page.worker
        if query_worker is not None and query_worker.isRunning():
            if not getattr(self, "_waiting_for_table", False):
                self._waiting_for_table = True
                query_worker.finished.connect(self.close)
            self.live_reading_page.stop_stream()
            self.data_recorder_page.recording_component.stop_recording()
            event.ignore()
            return
        live_worker = self.live_reading_page.worker
        if live_worker is not None and live_worker.isRunning():
            if not getattr(self, "_waiting_for_live", False):
                self._waiting_for_live = True
                live_worker.finished.connect(self.close)
            self.live_reading_page.stop_stream()
            self.data_recorder_page.recording_component.stop_recording()
            event.ignore()
            return
        worker = self.data_recorder_page.recording_worker
        if worker is not None and worker.isRunning():
            if not self._waiting_for_recording:
                self._waiting_for_recording = True
                worker.finished.connect(self.close)
            self.data_recorder_page.recording_component.stop_recording()
            event.ignore()
            return
        event.accept()
