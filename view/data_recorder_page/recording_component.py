from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout

from .widgets import add_field, input_field


class RecordingComponent(QFrame):
    """Recording settings, progress and start/stop actions."""
    recording_changed = Signal(bool)
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.connections_ready = False
        self.is_recording = False
        self.is_stopping = False
        self.status_text = "Idle"
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.recording_status = QLabel("Idle")
        self.recording_status.setStyleSheet("color: #718096; font-weight: 600;")
        self.setProperty("role", "card")
        recording = QVBoxLayout(self)
        recording.setContentsMargins(20, 20, 20, 20)
        recording.setSpacing(12)
        title = QLabel("Recording")
        title.setProperty("role", "cardTitle")
        recording.addWidget(title)
        recording.addWidget(self.recording_status)
        recording.addSpacing(4)
        self.sampling_input = QSpinBox()
        self.sampling_input.setRange(10, 10000)
        self.sampling_input.setValue(100)
        self.sampling_input.setSuffix(" ms")
        self.sampling_input.setMinimumHeight(38)
        self.table_input = input_field("")
        self.table_input.setText("kinova_feedback")
        add_field(recording, "Sampling interval", self.sampling_input)
        add_field(recording, "Table", self.table_input)
        recording.addSpacing(12)
        samples_label = QLabel("Samples recorded")
        samples_label.setProperty("role", "muted")
        recording.addWidget(samples_label)
        self.samples_value = QLabel("0")
        self.samples_value.setObjectName("samplesValue")
        recording.addWidget(self.samples_value)
        recording.addStretch()
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setSpacing(10)
        self.start_recording_button = QPushButton("Start Recording")
        self.start_recording_button.setProperty("role", "primary")
        self.stop_recording_button = QPushButton("Stop")
        for button in (self.start_recording_button, self.stop_recording_button):
            button.setMinimumHeight(42)

        self.buttons_layout.addWidget(self.start_recording_button, 2)
        self.buttons_layout.addWidget(self.stop_recording_button, 1)
        recording.addLayout(self.buttons_layout)
        self.start_recording_button.clicked.connect(self.start_recording)
        self.stop_recording_button.clicked.connect(self.stop_recording)
        self._update_controls()

    def set_connections_ready(self, db_connected, robot_connected):
        self.connections_ready = db_connected and robot_connected
        if not self.connections_ready and self.is_recording:
            self.stop_recording()
        self._update_controls()

    def start_recording(self):
        if not self.connections_ready or self.is_recording:
            return
        self.is_recording = True
        self.status_text = "Connecting..."
        self.recording_status.setToolTip("")
        self.samples_value.setText("0")
        self._update_controls()
        self.recording_changed.emit(True)
        self.start_requested.emit()

    def stop_recording(self):
        if not self.is_recording or self.is_stopping:
            return
        self.is_stopping = True
        self.status_text = "Stopping..."
        self._update_controls()
        self.stop_requested.emit()

    def mark_recording_started(self):
        if self.is_recording and not self.is_stopping:
            self.status_text = "Recording"
            self._update_controls()

    def finish_recording(self, error=""):
        self.is_recording = False
        self.is_stopping = False
        self.status_text = "Recording failed" if error else "Idle"
        self.recording_status.setToolTip(error)
        self._update_controls()
        self.recording_changed.emit(False)

    def _update_controls(self):
        self.start_recording_button.setEnabled(self.connections_ready and not self.is_recording)
        self.stop_recording_button.setEnabled(
            self.connections_ready and self.is_recording and not self.is_stopping
        )
        self.sampling_input.setEnabled(not self.is_recording)
        self.table_input.setEnabled(not self.is_recording)
        self.recording_status.setText(self.status_text)
        color = "#bd4652" if self.status_text == "Recording failed" else "#4caf78" if self.is_recording else "#718096"
        self.recording_status.setStyleSheet(f"color: {color}; font-weight: 600;")

    def set_compact(self, compact):
        self.buttons_layout.setDirection(
            QHBoxLayout.Direction.TopToBottom if compact
            else QHBoxLayout.Direction.LeftToRight
        )
