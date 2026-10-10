from datetime import datetime, timezone
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFrame, QScrollArea, QSplitter, QFormLayout,
                             QGridLayout, QTabWidget, QSizePolicy)
from view.kinova3DWidget import Kinova3DWidget
from .live_reading_worker import LiveReadingWorker

FIELDS = (("position", "Position", "°"), ("velocity", "Velocity", "°/s"),
          ("torque", "Torque", "N·m"), ("current", "Current", "A"),
          ("temperature", "Temperature", "°C"))
BASE_FIELDS = (("arm_voltage", "Arm voltage", "V"), ("arm_current", "Arm current", "A"),
               ("temperature_cpu", "CPU temperature", "°C"),
               ("temperature_ambient", "Ambient temperature", "°C"),
               *[(f"tool_pose_{a}", f"Tool {a.upper()}", "m") for a in ("x", "y", "z")],
               *[(f"tool_pose_theta_{a}", f"Tool θ{a.upper()}", "°") for a in ("x", "y", "z")])


class LiveReadingPage(QWidget):
    def __init__(self, robot_config_provider=None):
        super().__init__()
        self.robot_config_provider = robot_config_provider
        self.worker = None
        self._displayed = None
        self._error = ""
        self.setObjectName("liveReadingPage")
        self.setStyleSheet('''
            QLabel { background: transparent; }
            QLabel[heading="true"] { font-size: 18px; font-weight: 600; }
            QLabel#liveTitle { font-size: 26px; font-weight: 700; }
            QFrame[card="true"] { background: white; border: 1px solid #dde3ec; border-radius: 10px; }
            QPushButton { padding: 9px 12px; border: 1px solid #cfd7e3;
                border-radius: 7px; background: white; color: #2563eb; }
            QPushButton:disabled { color: #98a3b3; }
        ''')
        root = QVBoxLayout(self)
        self.root_layout = root
        self._layout_mode = None
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel("Kinova Live View")
        title.setObjectName("liveTitle")
        root.addWidget(title)
        root.addWidget(QLabel("Gen3 model • 6 joints • positions in degrees"))
        controls = QGridLayout()
        self.controls_layout = controls

        self.start_button = QPushButton("Start stream")
        self.start_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.stop_button = QPushButton("Stop stream")
        self.stop_button.setEnabled(False)
        reset = QPushButton("Recenter camera")
        self.reset_button = reset
        self.status = QLabel("Stopped")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root.addLayout(controls)
        root.addWidget(self.status)
        self.timestamp = QLabel("No data received")
        self.timestamp.setWordWrap(True)
        root.addWidget(self.timestamp)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter = splitter
        splitter.setChildrenCollapsible(False)
        self.robot = Kinova3DWidget()
        self.robot.setMinimumSize(240, 180)
        splitter.addWidget(self.robot)
        panel = QWidget()
        self.joint_panel = panel
        joints_layout = QVBoxLayout(panel)
        heading = QLabel("Joint Positions")
        heading.setProperty("heading", True)
        joints_layout.addWidget(heading)
        self.positions = []
        for i in range(6):
            card = QFrame()
            card.setProperty("card", True)
            row = QHBoxLayout(card)
            row.addWidget(QLabel(f"Joint {i+1}"))
            value = QLabel("—")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(value)
            self.positions.append(value)
            joints_layout.addWidget(card)
        joints_layout.addStretch()
        self.joint_scroll = QScrollArea()
        self.joint_scroll.setWidgetResizable(True)
        self.joint_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.joint_scroll.setWidget(panel)
        scroll = QScrollArea()
        self.details_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        details = QWidget()
        form = QFormLayout(details)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        heading = QLabel("All data")
        heading.setProperty("heading", True)
        form.addRow(heading)
        self.time_value = QLabel("—")
        self.time_value.setWordWrap(True)
        form.addRow("Time (UTC)", self.time_value)
        self.values = []
        for i in range(6):
            heading = QLabel(f"Joint {i+1}")
            heading.setProperty("heading", True)
            form.addRow(heading)
            values = {}
            for key, label, unit in FIELDS:
                value = QLabel("—")
                value.setAlignment(Qt.AlignmentFlag.AlignRight)
                form.addRow(label, value)
                values[key] = value
            self.values.append(values)
        form.addRow(QLabel("Base / Tool"))
        self.base_values = {}
        for key, label, unit in BASE_FIELDS:
            value = QLabel("—")
            form.addRow(label, value)
            self.base_values[key] = value
        scroll.setWidget(details)
        self.tabs = QTabWidget()
        self.tabs.setMinimumSize(240, 120)
        splitter.setStretchFactor(0, 1)
        root.addWidget(splitter, 1)
        note = QLabel("The robot uses the connection configured in Data Recorder.")
        note.setWordWrap(True)
        root.addWidget(note)
        self.start_button.clicked.connect(self.start_stream)
        self.stop_button.clicked.connect(self.stop_stream)
        reset.clicked.connect(self.robot.recenter_camera)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh)
        self.adapt_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "tabs"):
            self.adapt_layout()

    def adapt_layout(self):
        """Use available logical pixels, including Windows display scaling."""
        width = self.width()
        mode = "small" if width < 900 else "medium" if width < 1300 else "wide"
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        compact = mode == "small"
        margin = 12 if compact else 24
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.root_layout.setSpacing(8 if compact else 12)
        while self.controls_layout.count():
            self.controls_layout.takeAt(0)
        for column in range(4):
            self.controls_layout.setColumnStretch(column, 0)
        for column, button in enumerate((self.start_button, self.stop_button, self.reset_button)):
            self.controls_layout.addWidget(button, 0, column, Qt.AlignmentFlag.AlignLeft)
        self.controls_layout.setColumnStretch(3, 1)

        # Reparent the existing panels; retain telemetry and the 3D scene.
        self.joint_scroll.setParent(self)
        self.details_scroll.setParent(self)
        self.tabs.setParent(self)
        if mode == "wide":
            self.tabs.hide()
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
            self.splitter.addWidget(self.joint_scroll)
            self.splitter.addWidget(self.details_scroll)
            self.joint_scroll.show()
            self.details_scroll.show()
            self.splitter.setSizes([width * 6 // 10, width * 16 // 100, width * 24 // 100])
        else:
            self.tabs.addTab(self.joint_scroll, "Joint Positions")
            self.tabs.addTab(self.details_scroll, "All data")
            self.splitter.addWidget(self.tabs)
            self.tabs.show()
            self.splitter.setOrientation(Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal)
            self.splitter.setSizes([max(200, self.height() // 2), max(140, self.height() // 3)]
                                   if compact else [width * 6 // 10, width * 4 // 10])

    def start_stream(self):
        if self.worker is not None:
            return
        try:
            if self.robot_config_provider is None:
                raise ValueError("Configure the robot connection in Data Recorder")
            config = self.robot_config_provider()
            if config is None:
                raise ValueError("Configure the robot connection in Data Recorder")
            self._error = ""
            self._displayed = None
            self.worker = LiveReadingWorker(config, self)
            self.worker.failed.connect(self.show_error)
            self.worker.finished.connect(self.stream_finished)
            self.start_button.setEnabled(False)

            self.stop_button.setEnabled(True)
            self.status.setText("Starting…")
            self.worker.start()
            self.timer.start()
        except Exception as error:
            self.show_error(str(error))

    def show_error(self, message):
        self._error = message
        self.status.setText(f"Error: {message}")

    def stop_stream(self):
        if self.worker is not None:
            self.worker.request_stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")

    def stream_finished(self):
        self.timer.stop()
        self.worker.deleteLater()
        self.worker = None
        self.start_button.setEnabled(True)

        self.stop_button.setEnabled(False)
        if not self._error:
            self.status.setText("Stopped — last position retained")

    def refresh(self):
        if self.worker is None:
            return
        frame = self.worker.latest()
        if frame is None:
            return
        age = (datetime.now(timezone.utc) - frame["time"]).total_seconds()
        if not self._error and self.stop_button.isEnabled():
            self.status.setText("No new data received" if age > 2 else "Robot connected")
        if frame is self._displayed:
            return
        self._displayed = frame
        self.robot.set_joints(*[j["position"] for j in frame["joints"]])
        text = frame["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.timestamp.setText(f"Latest sample (UTC): {text}")
        self.time_value.setText(text)
        for i, joint in enumerate(frame["joints"]):
            self.positions[i].setText(f'{joint["position"]:.2f}°')
            for key, label, unit in FIELDS:
                self.values[i][key].setText(f"{joint[key]:.2f} {unit}")
        for key, label, unit in BASE_FIELDS:
            value = frame["base"].get(key)
            self.base_values[key].setText("—" if value is None else f"{value:.3f} {unit}")

    def hideEvent(self, event):
        self.stop_stream()
        super().hideEvent(event)
