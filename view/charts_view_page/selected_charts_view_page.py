"""Display the whole database selection using the same plots as live telemetry."""
from datetime import datetime, timezone
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton
from .charts_view_page import ChartsViewPage
from .chart_history import ChartHistory


def row_to_frame(row):
    """Map database columns to the shared live-chart telemetry structure."""
    stamp = row.get("time")
    if not isinstance(stamp, datetime):
        raise ValueError("The record does not have a valid timestamp")
    stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    base = {key: row.get(key) for key in (
        "arm_voltage", "arm_current", "temperature_cpu", "temperature_ambient")}
    for axis in ("x", "y", "z"):
        base[f"tool_pose_{axis}"] = row.get(f"tool_{axis}")
        base[f"tool_pose_theta_{axis}"] = row.get(f"tool_theta_{axis}")
    return dict(time=stamp, joints=[{field: row.get(f"joint_{i}_{field}")
                for field in ("position", "velocity", "torque", "current", "temperature")}
                for i in range(1, 7)], base=base)


class SelectedChartsViewPage(ChartsViewPage):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.history = ChartHistory(max_samples=None, max_age=None, allow_duplicates=True)
        self.title.setText("SELECTED DATA CHARTS")
        self.subtitle.setText("Charts include the entire selection in chronological order.")
        for widget in (self.start_button, self.stop_button, self.clear_button,
                       self.window, self.interval_label):
            widget.hide()
        self.back_button = QPushButton("Back to data")
        self.controls_layout.insertWidget(0, self.back_button)
        self.back_button.clicked.connect(self.back_requested.emit)
        self.note.setText("All selected records are retained. Change the metric, joints and projection; zoom in for details. Gaps longer than one second break the lines.")
        self.status.setText("Select records in Data Table and click «Show charts».")
        self.redraw()

    def start_stream(self):
        return  # This page displays database snapshots only.

    def visible_frames(self):
        return list(self.history.frames)

    def time_range(self, frames):
        first, last = frames[0]["t"], frames[-1]["t"]
        return (first, last) if first < last else (first-.5, last+.5)

    def set_selected_rows(self, rows):
        history = ChartHistory(max_samples=None, max_age=None, allow_duplicates=True)
        try:
            frames = sorted((row_to_frame(dict(row)) for row in rows), key=lambda f: f["time"])
            for frame in frames:
                history.append(frame)
        except (ValueError, TypeError, OverflowError) as error:
            self.status.setText(f"Invalid data: {error}")
            return False
        self.history = history
        self._hover_t = None
        self.cursor.hide()
        if frames:
            first = frames[0]["time"].isoformat(timespec="milliseconds")
            last = frames[-1]["time"].isoformat(timespec="milliseconds")
            self.status.setText(f"{len(frames)} selected records • UTC interval: {first} — {last}")
        else:
            self.status.setText("No records selected.")
        self.scroll_area.verticalScrollBar().setValue(0)
        for plot in [self.main_plot, *self.extra_plots, self.path_plot]:
            plot.enableAutoRange()
        self.redraw()
        return True

    def update_readout(self, frames):
        if frames:
            super().update_readout(frames)
        else:
            self.readout.setText("No records selected")
