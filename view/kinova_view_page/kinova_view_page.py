import math
import time
from bisect import bisect_right
from datetime import datetime, timezone
from statistics import median
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QFormLayout, QSplitter, QTabWidget, QSlider, QComboBox,
    QCheckBox, QSizePolicy)
from view.kinova3DWidget import Kinova3DWidget
from view.live_reading_page.live_reading_page import FIELDS
from view.data_recorder_page.recording_worker import COLUMNS
from view.data_table_page.data_table_worker import DataTableWorker

BASE_FIELDS = (("arm_voltage", "Arm voltage", "V"), ("arm_current", "Arm current", "A"),
    ("temperature_cpu", "CPU temperature", "°C"), ("temperature_ambient", "Ambient temperature", "°C"),
    *[(f"tool_{a}", f"Tool {a.upper()}", "m") for a in ("x", "y", "z")],
    *[(f"tool_theta_{a}", f"Tool θ{a.upper()}", "°") for a in ("x", "y", "z")])


def timestamp_seconds(value):
    if not isinstance(value, datetime):
        raise ValueError("The record does not have a valid timestamp")
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).timestamp()


def playback_offsets(rows, skip_gaps):
    """Preserve sample timing while optionally compressing recording breaks."""
    stamps = [timestamp_seconds(row["time"]) for row in rows]
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    positive = [gap for gap in gaps if gap > 0]
    typical = median(positive) if positive else .1
    threshold = max(1., typical * 10)
    offsets = [0.] if stamps else []
    for gap in gaps:
        offsets.append(offsets[-1] + (typical if skip_gaps and gap > threshold else gap))
    return offsets, (offsets[-1] + typical if offsets else 0.)


class KinovaViewPage(QWidget):
    def __init__(self, database_config_provider=None):
        super().__init__()
        self.database_config_provider = database_config_provider
        self.worker = None
        self.frames = []
        self.offsets = []
        self.frame_index = 0
        self.elapsed = 0.
        self.duration = 0.
        self._last_tick = 0.
        self._generation = 0
        self._selected_mode = False
        self._mode = None
        self.setObjectName("kinovaViewPage")
        self.setStyleSheet('''
            QLabel { background: transparent; }
            QLabel#twinTitle { font-size: 24px; font-weight: 700; }
            QLabel[heading="true"] { font-size: 18px; font-weight: 600; }
            QFrame[card="true"] { background: white; border: 1px solid #dde3ec; border-radius: 10px; }
            QPushButton, QComboBox { padding: 7px 10px; background: white; color: #2563eb;
                border: 1px solid #cfd7e3; border-radius: 7px; }
            QPushButton:disabled { color: #98a3b3; }
            QPushButton#replayPlay { background: #2563eb; color: white; }
            QPushButton#replayPlay:disabled { background: #a5baf1; }
            QTabWidget::pane { border: 1px solid #dde3ec; border-radius: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #aab6c8;
                border-radius: 3px; background: white; }
            QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
            QSlider::groove:horizontal { height: 4px; background: #dce3ef; border-radius: 2px; }
            QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px;
                background: #2563eb; }
        ''')
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 20, 20, 20)
        self.root.setSpacing(10)
        title = QLabel("KINOVA DIGITAL TWIN")
        title.setObjectName("twinTitle")
        self.root.addWidget(title)
        source_row = QHBoxLayout()
        self.source_label = QLabel("Latest available record")
        self.source_label.setWordWrap(True)
        source_row.addWidget(self.source_label, 1)
        self.refresh_button = QPushButton("↻ Latest position")
        self.latest_100_button = QPushButton("Lastest 100")
        self.camera_button = QPushButton("Recenter camera")
        source_row.addWidget(self.refresh_button)
        source_row.addWidget(self.latest_100_button)
        source_row.addWidget(self.camera_button)
        self.root.addLayout(source_row)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.robot = Kinova3DWidget()
        self.robot.setMinimumSize(240, 180)
        self.robot.plotter.set_background("#202224")
        for actor in self.robot.robot_actors.values():
            actor.prop.interpolation = "phong"
            actor.prop.ambient = .35
            actor.prop.diffuse = .75
            actor.prop.specular = .2
        self.splitter.addWidget(self.robot)
        joint_panel = QWidget()
        joints_layout = QVBoxLayout(joint_panel)
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
            joints_layout.addWidget(card)
            self.positions.append(value)
        joints_layout.addStretch()
        self.joint_scroll = QScrollArea()
        self.joint_scroll.setWidgetResizable(True)
        self.joint_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.joint_scroll.setWidget(joint_panel)
        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setFrameShape(QFrame.Shape.NoFrame)
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
        self.details_scroll.setWidget(details)
        self.tabs = QTabWidget()
        self.tabs.setMinimumSize(240, 120)
        self.splitter.setStretchFactor(0, 1)
        self.root.addWidget(self.splitter, 1)
        controls = QHBoxLayout()
        self.play_button = QPushButton("▶ Play")
        self.play_button.setObjectName("replayPlay")
        self.pause_button = QPushButton("Ⅱ Pause")
        self.stop_button = QPushButton("■ Stop")
        self.loop = QCheckBox("Loop")
        self.skip_gaps = QCheckBox("Skip recording gaps")
        self.skip_gaps.setChecked(True)
        self.skip_gaps.setToolTip("Compress gaps longer than 1 second and 10 typical sample intervals")
        for button in (self.play_button, self.pause_button, self.stop_button):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            controls.addWidget(button)
        controls.addWidget(self.loop)
        controls.addWidget(self.skip_gaps)
        controls.addStretch()
        self.root.addLayout(controls)
        self.status = QLabel("No data loaded")
        self.status.setWordWrap(True)
        self.root.addWidget(self.status)
        timeline = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.speed = QComboBox()
        for factor in (.25, .5, 1., 1.5, 2., 4.):
            self.speed.addItem(f"{factor:g}×", factor)
        self.speed.setCurrentIndex(2)
        self.speed.setToolTip("Playback speed")
        timeline.addWidget(self.slider, 1)
        timeline.addWidget(QLabel("Speed"))
        timeline.addWidget(self.speed)
        self.root.addLayout(timeline)
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.tick)
        self.play_button.clicked.connect(self.play)
        self.pause_button.clicked.connect(self.pause)
        self.stop_button.clicked.connect(self.stop)
        self.slider.valueChanged.connect(self.seek)
        self.speed.currentIndexChanged.connect(self.change_speed)
        self.skip_gaps.toggled.connect(self.change_timing)
        self._speed = 1.
        self.refresh_button.clicked.connect(self.load_latest)
        self.latest_100_button.clicked.connect(lambda: self.load_latest_records(100))
        self.camera_button.clicked.connect(self.robot.recenter_camera)
        self.update_controls()
        self.adapt_layout()

    def update_controls(self):
        playable = len(self.frames) > 1
        self.play_button.setEnabled(playable and not self.timer.isActive())
        self.pause_button.setEnabled(self.timer.isActive())
        self.stop_button.setEnabled(playable)
        self.slider.setEnabled(playable)
        self.speed.setEnabled(playable)
        self.loop.setEnabled(playable)
        self.skip_gaps.setEnabled(playable)

    def load_latest(self):
        self.load_latest_records(1)

    def load_latest_records(self, limit):
        if self.worker is not None:
            return
        self.stop()
        self._generation += 1
        generation = self._generation
        try:
            if self.database_config_provider is None:
                raise ValueError("Configure PostgreSQL in Data Recorder")
            config = self.database_config_provider()
            self.worker = DataTableWorker(config, limit=limit, parent=self)
            self.worker.loaded.connect(lambda rows: self.receive_latest(rows, generation))
            self.worker.failed.connect(lambda error: self.query_failed(error, generation))
            self.worker.finished.connect(self.query_finished)
            self.refresh_button.setEnabled(False)
            self.latest_100_button.setEnabled(False)
            self.status.setText("Loading the latest position from the database…" if limit == 1
                                else "Loading the latest 100 records from the database…")
            self.worker.start()
        except Exception as error:
            self.query_failed(str(error), generation)

    def receive_latest(self, rows, generation):
        if generation != self._generation:
            return
        self.set_frames([dict(zip(COLUMNS, row)) for row in rows], selected=False)

    def query_failed(self, error, generation):
        if generation == self._generation:
            self.status.setText(f"PostgreSQL error: {error}")

    def query_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.refresh_button.setEnabled(True)
        self.latest_100_button.setEnabled(True)

    def set_selected_rows(self, rows):
        self._generation += 1  # Ignore any pending latest-position result.
        return self.set_frames(rows, selected=True)

    def set_frames(self, rows, selected):
        try:
            ordered = sorted((dict(row) for row in rows), key=lambda row: timestamp_seconds(row["time"]))
            for row in ordered:
                if not all(math.isfinite(float(row[f"joint_{i}_position"])) for i in range(1, 7)):
                    raise ValueError("Joint positions must be finite")
        except (ValueError, KeyError, TypeError) as error:
            self.status.setText(f"Invalid data: {error}")
            return False
        self.timer.stop()
        self.frames = ordered
        self._selected_mode = selected
        self.frame_index = 0
        self.elapsed = 0.
        self.offsets, self.duration = playback_offsets(ordered, self.skip_gaps.isChecked())
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(ordered)-1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.source_label.setText(f"Table selection — {len(ordered)} records in chronological order"
                                 if selected else
                                 f"Latest {len(ordered)} records in chronological order"
                                 if len(ordered) > 1 else "Latest available record")
        if ordered:
            self.display_frame(0)
            self.status.setText("Stopped" if len(ordered) > 1 else "Position loaded from the database")
            self.robot.recenter_camera()
        else:
            for value in [*self.positions, self.time_value, *self.base_values.values(),
                          *(value for joint in self.values for value in joint.values())]:
                value.setText("—")
            self.status.setText("No records in the table")
        self.update_controls()
        return True

    def display_frame(self, index):
        if not self.frames:
            return
        self.frame_index = index
        frame = self.frames[index]
        self.robot.set_joints(*[float(frame[f"joint_{i}_position"]) for i in range(1, 7)])
        value = frame["time"]
        utc = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        self.time_value.setText(utc.isoformat(timespec="milliseconds"))
        for i in range(6):
            self.positions[i].setText(f'{float(frame[f"joint_{i+1}_position"]):.2f}°')
            for key, label, unit in FIELDS:
                value = frame.get(f"joint_{i+1}_{key}")
                self.values[i][key].setText("—" if value is None else f"{value:.4f} {unit}")
        for key, label, unit in BASE_FIELDS:
            value = frame.get(key)
            self.base_values[key].setText("—" if value is None else f"{value:.4f} {unit}")
        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)

    def play(self):
        if len(self.frames) < 2 or self.timer.isActive():
            return
        if self.elapsed >= self.duration:
            self.elapsed = 0.
            self.display_frame(0)
        self._last_tick = time.monotonic()
        self.timer.start()
        self.status.setText(f"Playing — {self.frame_index+1}/{len(self.frames)}")
        self.update_controls()

    def tick(self):
        now = time.monotonic()
        self.elapsed += (now - self._last_tick) * self._speed
        self._last_tick = now
        if self.elapsed >= self.duration:
            if self.loop.isChecked():
                self.elapsed %= self.duration
            else:
                self.display_frame(len(self.frames)-1)
                self.timer.stop()
                self.status.setText("Playback finished")
                self.update_controls()
                return
        index = min(len(self.frames)-1, max(0, bisect_right(self.offsets, self.elapsed)-1))
        if index != self.frame_index:
            self.display_frame(index)
        self.status.setText(f"Playing — {index+1}/{len(self.frames)}")

    def pause(self):
        if self.timer.isActive():
            self.tick()
            self.timer.stop()
            self.status.setText(f"Paused — {self.frame_index+1}/{len(self.frames)}")
        self.update_controls()

    def stop(self):
        self.timer.stop()
        self.elapsed = 0.
        if self.frames:
            self.display_frame(0)
            self.status.setText("Stopped")
        self.update_controls()

    def seek(self, index):
        if not self.frames:
            return
        self.elapsed = self.offsets[index]
        self._last_tick = time.monotonic()
        self.display_frame(index)
        self.status.setText(f'{"Playing" if self.timer.isActive() else "Paused"} — {index+1}/{len(self.frames)}')

    def change_timing(self, _checked):
        self.offsets, self.duration = playback_offsets(self.frames, self.skip_gaps.isChecked())
        if self.frames:
            self.seek(self.frame_index)

    def change_speed(self, _index):
        if self.timer.isActive():
            self.tick()
        self._speed = self.speed.currentData()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.frames and self.worker is None:
            QTimer.singleShot(0, self.load_latest)

    def hideEvent(self, event):
        self.pause()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "tabs"):
            self.adapt_layout()

    def adapt_layout(self):
        width = self.width()
        mode = "small" if width < 900 else "medium" if width < 1300 else "wide"
        if mode == self._mode:
            return
        self._mode = mode
        margin = 12 if mode == "small" else 20
        self.root.setContentsMargins(margin, margin, margin, margin)
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
            self.splitter.setSizes([width*5//10, width*22//100, width*28//100])
        else:
            self.tabs.addTab(self.joint_scroll, "Joint Positions")
            self.tabs.addTab(self.details_scroll, "All data")
            self.splitter.addWidget(self.tabs)
            self.tabs.show()
            self.splitter.setOrientation(Qt.Orientation.Vertical if mode == "small" else Qt.Orientation.Horizontal)
            self.splitter.setSizes([max(200, self.height()//2), max(140, self.height()//3)]
                                   if mode == "small" else [width*6//10, width*4//10])
