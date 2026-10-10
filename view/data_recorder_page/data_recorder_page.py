from PySide6.QtCore import QEvent, Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)


from .connections_component import ConnectionsComponent
from .recording_component import RecordingComponent
from .recording_worker import RecordingWorker, build_insert_sql


class DataRecorderPage(QWidget):
    """Recorder configuration with layouts based on the available viewport."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Recorder")
        self.setObjectName("dataRecorderPage")
        self._layout_mode = None
        self.recording_worker = None
        self._recording_error = ""
        self.setStyleSheet("""
            QWidget#dataRecorderPage, QWidget#recorderCanvas {
                background: #f3f5f9; color: #243247;
            }
            QWidget#dataRecorderPage QLabel {
                background-color: transparent; color: #243247; font-size: 13px;
            }
            QWidget#dataRecorderPage QLabel[role="title"] {
                font-size: 26px; font-weight: 700;
            }
            QWidget#dataRecorderPage QLabel[role="muted"] { color: #718096; }
            QWidget#dataRecorderPage QLabel[role="cardTitle"] {
                font-size: 16px; font-weight: 700;
            }
            QFrame[role="card"] {
                background: white; border: 1px solid #dde3ec; border-radius: 12px;
            }
            QWidget#dataRecorderPage QLineEdit, QWidget#dataRecorderPage QSpinBox {
                background: #f9fafc; color: #243247; border: 1px solid #cfd7e3;
                border-radius: 6px; padding: 7px 10px; font-size: 13px;
                selection-background-color: #2563eb;
            }
            QWidget#dataRecorderPage QLineEdit:focus,
            QWidget#dataRecorderPage QSpinBox:focus { border-color: #2563eb; }
            QWidget#dataRecorderPage QPushButton {
                background: white; color: #334155; border: 1px solid #cfd7e3;
                border-radius: 7px; padding: 9px 14px; font-weight: 600;
            }
            QWidget#dataRecorderPage QPushButton:hover { background: #edf2fa; }
            QWidget#dataRecorderPage QPushButton[role="primary"] {
                background: #2563eb; color: white; border-color: #2563eb;
            }
            QWidget#dataRecorderPage QPushButton[role="primary"]:hover {
                background: #1d4ed8;
            }
            QWidget#dataRecorderPage QPushButton:disabled {
                background: #edf0f5; color: #98a3b3; border-color: #e0e5ed;
            }
            QWidget#dataRecorderPage QLabel#samplesValue {
                font-size: 44px; font-weight: 700; color: #2563eb;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll_area)

        canvas = QWidget()
        canvas.setObjectName("recorderCanvas")
        self.canvas_layout = QVBoxLayout(canvas)
        self.canvas_layout.setContentsMargins(24, 28, 24, 28)
        self.content_widget = QWidget()
        self.content_widget.setMaximumWidth(1200)
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.canvas_layout.addWidget(self.content_widget, 0, Qt.AlignmentFlag.AlignHCenter)
        self.canvas_layout.addStretch()
        main = QVBoxLayout(self.content_widget)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(24)

        header = QVBoxLayout()
        header.setSpacing(6)
        title = QLabel("Data logging")
        title.setProperty("role", "title")
        description = QLabel("Configure connections and record Kinova Gen3 data")
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(description)
        main.addLayout(header)

        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(20)
        main.addLayout(self.cards_layout)
        self.connections_component = ConnectionsComponent()
        self.recording_component = RecordingComponent()
        self.connections_component.connections_changed.connect(
            self.recording_component.set_connections_ready
        )
        self.recording_component.recording_changed.connect(
            lambda recording: self.connections_component.setEnabled(not recording)
        )
        self.recording_component.start_requested.connect(self._start_acquisition)
        self.recording_component.stop_requested.connect(self._stop_acquisition)

        # Keep the page's public widget attributes available to callers.
        for name in (
            "robot_ip_input", "robot_username_input", "robot_password_input",
            "robot_port_input", "robot_status", "db_host_input", "db_port_input",
            "db_name_input", "db_user_input", "db_password_input", "db_status",
            "test_connections_button",
        ):
            setattr(self, name, getattr(self.connections_component, name))
        for name in (
            "sampling_input", "table_input", "samples_value", "recording_status",
            "start_recording_button", "stop_recording_button",
        ):
            setattr(self, name, getattr(self.recording_component, name))

        self.scroll_area.setWidget(canvas)
        self.scroll_area.viewport().installEventFilter(self)
        self._update_layout()

    @Slot()
    def _start_acquisition(self):
        if self.recording_worker is not None:
            return
        c = self.connections_component
        r = self.recording_component
        self._recording_error = ""
        try:
            insert_sql = build_insert_sql(r.table_input.text())
            config = {
                "database": {
                    "host": c.db_host_input.text().strip(),
                    "port": c.db_port_input.text().strip(),
                    "dbname": c.db_name_input.text().strip(),
                    "user": c.db_user_input.text().strip(),
                    "password": c.db_password_input.text(),
                },
                "robot": {
                    "host": c.robot_ip_input.text().strip(),
                    "port": int(c.robot_port_input.text().strip()),
                    "username": c.robot_username_input.text().strip(),
                    "password": c.robot_password_input.text(),
                },
                "interval": r.sampling_input.value() / 1000.0,
            }
            worker = RecordingWorker(config, insert_sql, self)
            self.recording_worker = worker
            worker.recording_started.connect(r.mark_recording_started)
            worker.samples_saved.connect(self._update_samples)
            worker.failed.connect(self._recording_failed)
            worker.finished.connect(self._acquisition_finished)
            worker.start()
        except Exception as error:
            self.recording_worker = None
            r.finish_recording(str(error))

    @Slot()
    def _stop_acquisition(self):
        if self.recording_worker is not None:
            self.recording_worker.request_stop()

    @Slot(int)
    def _update_samples(self, count):
        self.samples_value.setText(str(count))

    @Slot(str)
    def _recording_failed(self, error):
        self._recording_error = error
        # Re-test both services before another attempt after an acquisition error.
        self.connections_component._invalidate_connection("db")
        self.connections_component._invalidate_connection("robot")

    @Slot()
    def _acquisition_finished(self):
        worker = self.recording_worker
        self.recording_worker = None
        self.recording_component.finish_recording(self._recording_error)
        if worker is not None:
            worker.deleteLater()

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            self._update_layout()
        return super().eventFilter(watched, event)

    def _update_layout(self):
        width = self.scroll_area.viewport().width()
        mode = "wide" if width >= 1050 else "medium" if width >= 640 else "small"
        margin = 16 if mode == "small" else 24
        self.canvas_layout.setContentsMargins(margin, 24, margin, 24)
        self.content_widget.setFixedWidth(max(0, min(1200, width - 2 * margin)))
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        while self.cards_layout.count():
            self.cards_layout.takeAt(0)
        self.cards_layout.setColumnStretch(0, 2 if mode == "wide" else 1)
        self.cards_layout.setColumnStretch(1, 1 if mode == "wide" else 0)
        self.connections_component.set_compact(mode == "small")
        self.recording_component.set_compact(mode == "small")
        self.cards_layout.addWidget(self.connections_component, 0, 0)
        self.cards_layout.addWidget(self.recording_component,
                                   0 if mode == "wide" else 1,
                                   1 if mode == "wide" else 0)
