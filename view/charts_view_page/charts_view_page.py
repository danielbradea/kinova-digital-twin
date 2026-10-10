from datetime import datetime, timezone
import math
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QScrollArea, QFrame, QGridLayout, QSizePolicy)
import pyqtgraph as pg
from .charts_worker import ChartsWorker
from .chart_history import ChartHistory, curve_data

COLORS = ("#2563eb", "#f97316", "#10b981", "#a855f7", "#ef4444", "#0891b2")
METRICS = (("position", "Position", "°"), ("velocity", "Velocity", "°/s"),
           ("torque", "Torque", "N·m"), ("current", "Current", "A"),
           ("temperature", "Temperature", "°C"))


def formatted(value, unit=""):
    return f"{value:.2f} {unit}".strip() if value is not None and math.isfinite(value) else "—"

class ChartsViewPage(QWidget):
    def __init__(self, robot_config_provider=None):
        super().__init__()
        self.robot_config_provider = robot_config_provider
        self.worker = None
        self.history = ChartHistory()
        self._error = ""
        self._columns = None
        self._hover_t = None
        self.setObjectName("chartsViewPage")
        self.setStyleSheet('''
            QLabel { background: transparent; }
            QLabel#chartsTitle { font-size: 24px; font-weight: 700; }
            QLabel[heading="true"] { font-size: 16px; font-weight: 600; }
            QFrame[card="true"] { background: white; border: 1px solid #dde3ec; border-radius: 12px; }
            QPushButton, QComboBox { padding: 7px 10px; background: white; color: #2563eb;
                border: 1px solid #cfd7e3; border-radius: 7px; }
            QPushButton:disabled { color: #98a3b3; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #aab6c8;
                border-radius: 3px; background: white; }
            QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
            QCheckBox { background: transparent; }
        ''')
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        title = QLabel("KINOVA LIVE CHARTS")
        self.title = title
        title.setObjectName("chartsTitle")
        root.addWidget(title)
        self.subtitle = QLabel("Real-time telemetry • 6 joints • connection from Data Recorder")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)
        controls = QHBoxLayout()
        self.controls_layout = controls
        self.start_button = QPushButton("Start stream")
        self.stop_button = QPushButton("Stop stream")
        self.clear_button = QPushButton("Clear history")
        self.stop_button.setEnabled(False)
        for button in (self.start_button, self.stop_button, self.clear_button):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            controls.addWidget(button)
        controls.addStretch()
        root.addLayout(controls)
        self.status = QLabel("Stopped")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        canvas = QWidget()
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        toolbar = QHBoxLayout()
        self.interval_label = QLabel("Visible interval")
        toolbar.addWidget(self.interval_label)
        self.window = QComboBox()
        for seconds in (30, 60, 120):
            self.window.addItem(f"{seconds} seconds", seconds)
        toolbar.addWidget(self.window)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.stats = QLabel("Latest sample: —    Samples: 0    Rate: —    Power: —")
        self.stats.setWordWrap(True)
        layout.addWidget(self.stats)
        main_card, main_layout = self.card("Joints")
        metric_row = QHBoxLayout()
        metric_row.addWidget(QLabel("Metric"))
        self.metric = QComboBox()
        for key, label, unit in METRICS:
            self.metric.addItem(f"{label} ({unit})", key)
        metric_row.addWidget(self.metric)
        metric_row.addStretch()
        main_layout.addLayout(metric_row)
        legend = QHBoxLayout()
        self.joints = []
        for i, color in enumerate(COLORS):
            checkbox = QCheckBox(f"J{i+1}")
            checkbox.setChecked(True)
            checkbox.setStyleSheet(f"color: {color};")
            self.joints.append(checkbox)
            legend.addWidget(checkbox)
            checkbox.toggled.connect(self.redraw)
        legend.addStretch()
        main_layout.addLayout(legend)
        self.main_plot = self.plot("°")
        self.main_plot.setMinimumHeight(280)
        self.main_plot.setMaximumHeight(320)
        self.joint_curves = [self.main_plot.plot(pen=pg.mkPen(color, width=2), connect="finite") for color in COLORS]
        main_layout.addWidget(self.main_plot)
        self.cursor = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#94a3b8", style=Qt.PenStyle.DashLine))
        self.main_plot.addItem(self.cursor, ignoreBounds=True)
        self.cursor.hide()
        self.readout = QLabel("Waiting for robot data")
        self.readout.setWordWrap(True)
        main_layout.addWidget(self.readout)
        layout.addWidget(main_card)
        self.mouse_proxy = pg.SignalProxy(self.main_plot.scene().sigMouseMoved, rateLimit=20, slot=self.hover)
        self.grid = QGridLayout()
        self.grid.setSpacing(14)
        self.cards = []
        self.extra_plots = []
        self.series = []
        definitions = (
            ("Estimated electrical power — P = U × I", "W", (("power", "Power"),)),
            ("Temperatures", "°C", (("temperature_cpu", "CPU"), ("temperature_ambient", "Ambient"))),
            ("Tool coordinates", "m", (("tool_pose_x", "X"), ("tool_pose_y", "Y"), ("tool_pose_z", "Z"))),
        )
        for title, unit, series in definitions:
            card, card_layout = self.card(title)
            plot = self.plot(unit)
            plot.addLegend()
            curves = [(key, plot.plot(name=label, pen=pg.mkPen(COLORS[i], width=2), connect="finite"))
                      for i, (key, label) in enumerate(series)]
            card_layout.addWidget(plot)
            self.cards.append(card)
            self.extra_plots.append(plot)
            self.series.extend(curves)
        path_card, path_layout = self.card("Tool trajectory")
        projection_row = QHBoxLayout()
        projection_row.addWidget(QLabel("Projection"))
        self.projection = QComboBox()
        self.projection.addItems(["XY", "XZ", "YZ"])
        projection_row.addWidget(self.projection)
        projection_row.addStretch()
        path_layout.addLayout(projection_row)
        self.path_plot = self.plot("m", time_axis=False)
        self.path_plot.setAspectLocked(True)
        self.path_curve = self.path_plot.plot(pen=pg.mkPen(COLORS[2], width=2), connect="finite")
        self.path_point = self.path_plot.plot(pen=None, symbol="o", symbolSize=8, symbolBrush=COLORS[2])
        path_layout.addWidget(self.path_plot)
        self.cards.append(path_card)
        layout.addLayout(self.grid)
        note = QLabel("History: up to 120 seconds / 2400 samples. Gaps longer than one second break the lines. Joint angles are continuously unwrapped.")
        self.note = note
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll.setWidget(canvas)
        root.addWidget(scroll, 1)
        self.scroll_area = scroll
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh)
        self.start_button.clicked.connect(self.start_stream)
        self.stop_button.clicked.connect(self.stop_stream)
        self.clear_button.clicked.connect(self.clear_history)
        self.window.currentIndexChanged.connect(self.redraw)
        self.metric.currentIndexChanged.connect(self.redraw)
        self.projection.currentIndexChanged.connect(self.redraw)
        self.arrange_cards()
        self.redraw()

    @staticmethod
    def card(title):
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        heading = QLabel(title)
        heading.setProperty("heading", True)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        return card, layout

    @staticmethod
    def plot(unit, time_axis=True):
        axes = {"bottom": pg.DateAxisItem(utcOffset=0)} if time_axis else None
        plot = pg.PlotWidget(background="white", axisItems=axes)
        plot.setMinimumHeight(230)
        plot.setMaximumHeight(250)
        plot.setMinimumWidth(100)
        plot.showGrid(x=True, y=True, alpha=.15)
        plot.setLabel("left", units=unit)
        plot.setLabel("bottom", "Time (UTC)" if time_axis else "X", units=None if time_axis else "m")
        for axis in ("left", "bottom"):
            plot.getAxis(axis).setTextPen("#475569")
            plot.getAxis(axis).setPen("#cbd5e1")
        return plot

    def arrange_cards(self):
        columns = 1 if self.width() < 1050 else 2
        if self._columns == columns:
            return
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // columns, i % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "cards"):
            self.arrange_cards()

    def start_stream(self):
        if self.worker is not None:
            return
        try:
            if self.robot_config_provider is None:
                raise ValueError("Configure the robot connection in Data Recorder")
            worker = ChartsWorker(self.robot_config_provider(), self)
            self.worker = worker
            self._error = ""
            self.clear_history()
            worker.failed.connect(self.failed)
            worker.finished.connect(self.finished)
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status.setText("Connecting to robot…")
            worker.start()
            self.timer.start()
        except Exception as error:
            self.failed(str(error))

    def failed(self, error):
        self._error = error
        self.status.setText(f"Error: {error}")

    def stop_stream(self):
        if self.worker is not None:
            self.refresh()
            self.worker.request_stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")

    def finished(self):
        self.refresh()
        self.timer.stop()
        self.worker.deleteLater()
        self.worker = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if not self._error:
            self.status.setText("Stopped — charts retained")

    def refresh(self):
        if self.worker is None:
            return
        frames = self.worker.drain()
        for frame in frames:
            self.history.append(frame)
        if not self._error and self.stop_button.isEnabled() and self.history.frames:
            age = datetime.now(timezone.utc).timestamp() - self.history.frames[-1]["t"]
            self.status.setText("Robot connected" if age <= 2 else "No new data received")
        if frames:
            self.redraw()

    def clear_history(self):
        if self.worker is not None:
            self.worker.drain()
        self.history.clear()
        self._hover_t = None
        self.cursor.hide()
        self.redraw()

    def visible_frames(self):
        return self.history.window(self.window.currentData())

    def time_range(self, frames):
        return frames[-1]["t"] - self.window.currentData(), frames[-1]["t"]

    def redraw(self, *_args):
        frames = self.visible_frames()
        metric = self.metric.currentData()
        unit = next(unit for key, label, unit in METRICS if key == metric)
        self.main_plot.setLabel("left", units=unit)
        for i, curve in enumerate(self.joint_curves, 1):
            curve.setVisible(self.joints[i-1].isChecked())
            key = f'j{i}_{"continuous" if metric == "position" else metric}'
            curve.setData(*curve_data(frames, key), connect="finite")
        for key, curve in self.series:
            curve.setData(*curve_data(frames, key), connect="finite")
        if frames:
            last = frames[-1]
            for plot in [self.main_plot, *self.extra_plots]:
                plot.setXRange(*self.time_range(frames), padding=0)
            duration = last["t"] - frames[0]["t"]
            rate = (len(frames)-1)/duration if duration > 0 else None
            stamp = datetime.fromtimestamp(last["t"], timezone.utc).strftime("%H:%M:%S UTC")
            self.stats.setText(f'Latest sample: {stamp}    Samples: {len(frames)}    Rate: {formatted(rate, "Hz")}    Power: {formatted(last.get("power"), "W")}')
        else:
            self.stats.setText("Latest sample: —    Samples: 0    Rate: —    Power: —")
        a, b = self.projection.currentText().lower()
        self.path_plot.setLabel("bottom", a.upper(), units="m")
        self.path_plot.setLabel("left", b.upper(), units="m")
        self.path_curve.setData(*curve_data(frames, f"tool_pose_{b}", f"tool_pose_{a}"), connect="finite")
        valid = [f for f in frames if math.isfinite(f.get(f"tool_pose_{a}", float("nan")))
                 and math.isfinite(f.get(f"tool_pose_{b}", float("nan")))]
        self.path_point.setData([valid[-1][f"tool_pose_{a}"]] if valid else [],
                                [valid[-1][f"tool_pose_{b}"]] if valid else [])
        self.update_readout(frames)

    def hover(self, event):
        point = event[0]
        if self.main_plot.sceneBoundingRect().contains(point):
            self._hover_t = self.main_plot.getViewBox().mapSceneToView(point).x()
            self.cursor.setPos(self._hover_t)
            self.cursor.show()
        else:
            self._hover_t = None
            self.cursor.hide()
        self.update_readout(self.visible_frames())

    def update_readout(self, frames):
        if not frames:
            self.readout.setText("Waiting for robot data")
            return
        frame = min(frames, key=lambda f: abs(f["t"]-self._hover_t)) if self._hover_t is not None else frames[-1]
        metric = self.metric.currentData()
        unit = next(unit for key, label, unit in METRICS if key == metric)
        value_key = "continuous" if metric == "position" else metric
        fields = [f'J{i+1}: {formatted(frame.get(f"j{i+1}_{value_key}"), unit)}'
                  for i, joint in enumerate(self.joints) if joint.isChecked()]
        stamp = datetime.fromtimestamp(frame["t"], timezone.utc).strftime("%H:%M:%S UTC")
        self.readout.setText(stamp + " · " + " · ".join(fields) if fields else "Select at least one joint")

    def hideEvent(self, event):
        self.stop_stream()
        super().hideEvent(event)
