from datetime import datetime, timedelta, timezone
from numbers import Number
from PySide6.QtCore import (Qt, QAbstractTableModel, QModelIndex, Signal, QTime, QDateTime, QTimeZone, QTimer, QSize)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDateEdit, QTimeEdit, QTableView, QHeaderView,
    QAbstractItemView, QSizePolicy, QLayout)
from view.data_recorder_page.recording_worker import COLUMNS
from .data_table_worker import DataTableWorker, SEARCH_LIMIT

DISPLAY_ZONE = QTimeZone(b"Europe/Bucharest")
# Filters and table timestamps use local time; database queries use UTC.


def column_title(column):
    if column == "time":
        return "Time"
    if column.startswith("joint_"):
        _, joint, field = column.split("_", 2)
        unit = {"position": "°", "velocity": "°/s", "torque": "N·m",
                "current": "A", "temperature": "°C"}[field]
        return f"J{joint} {field.title()} ({unit})"
    return column.replace("_", " ").title()


class FeedbackTableModel(QAbstractTableModel):
    selection_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.checked = set()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS) + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if index.column() == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if index.row() in self.checked else Qt.CheckState.Unchecked
            return None
        value = self.rows[index.row()][index.column() - 1]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft
                       if index.column() == 1 else Qt.AlignmentFlag.AlignRight))
        if role == Qt.ItemDataRole.ToolTipRole:
            return "—" if value is None else str(value)
        if role == Qt.ItemDataRole.DisplayRole:
            if value is None:
                return "—"
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3]
                date = QDateTime.fromMSecsSinceEpoch(int(value.timestamp()*1000), DISPLAY_ZONE)
                return date.toString("dd.MM.yyyy HH:mm:ss.zzz")
            if isinstance(value, Number):
                return f"{value:.4f}"
            return str(value)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return "✓" if section == 0 else column_title(COLUMNS[section - 1])

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsUserCheckable if index.column() == 0 else flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        if value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value):
            self.checked.add(index.row())
        else:
            self.checked.discard(index.row())
        self.dataChanged.emit(index, index, [role])
        self.selection_changed.emit(len(self.checked))
        return True

    def replace_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.checked.clear()
        self.endResetModel()
        self.selection_changed.emit(0)

    def toggle_all(self, section):
        if section != 0 or not self.rows:
            return
        self.checked = set() if len(self.checked) == len(self.rows) else set(range(len(self.rows)))
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows)-1, 0),
                              [Qt.ItemDataRole.CheckStateRole])
        self.selection_changed.emit(len(self.checked))

    def selected_rows(self):
        return [dict(zip(COLUMNS, self.rows[i])) for i in sorted(self.checked)]

class DataTablePage(QWidget):
    replay_requested = Signal(object)
    charts_requested = Signal(object)

    def __init__(self, database_config_provider=None):
        super().__init__()
        self.database_config_provider = database_config_provider
        self.worker = None
        self._loaded_once = False
        self._layout_compact = None
        self._request_text = ""
        self._limit = 100
        self.setObjectName("dataTablePage")
        self.setStyleSheet('''
            QWidget#dataTablePage QLabel { background: transparent; }
            QLabel#dataTableTitle { font-size: 24px; font-weight: 700; }
            QPushButton, QDateEdit, QTimeEdit { background: white; border: 1px solid #cfd7e3;
                border-radius: 7px; padding: 7px 10px; }
            QPushButton#searchData { background: #2563eb; color: white; }
            QPushButton:disabled { color: #98a3b3; }
            QTableView { background: white; alternate-background-color: #f5f7fb;
                border: 1px solid #dde3ec; border-radius: 8px; gridline-color: #edf0f5; }
            QHeaderView::section { background: #f3f5f9; padding: 7px; border: none;
                border-bottom: 1px solid #dde3ec; }
        ''')
        self.root = QVBoxLayout(self)
        self.root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.root.setContentsMargins(20, 20, 20, 20)
        self.root.setSpacing(12)
        title = QLabel("KINOVA DATA")
        title.setObjectName("dataTableTitle")
        self.root.addWidget(title)
        self.filters = QGridLayout()
        self.filter_widgets = []
        self.from_date, self.to_date = QDateEdit(), QDateEdit()
        self.from_time, self.to_time = QTimeEdit(), QTimeEdit()
        today = QDateTime.currentDateTime().toTimeZone(DISPLAY_ZONE).date()
        for date in (self.from_date, self.to_date):
            date.setCalendarPopup(True)
            date.setDisplayFormat("dd.MM.yyyy")
            date.setDate(today)
        for time in (self.from_time, self.to_time):
            time.setDisplayFormat("HH:mm:ss")
        self.from_time.setTime(QTime(0, 0, 0))
        self.to_time.setTime(QTime(23, 59, 59))
        for text, editor in (("Start date", self.from_date), ("Start time", self.from_time),
                              ("End date", self.to_date), ("End time", self.to_time)):
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(QLabel(text))
            layout.addWidget(editor)
            self.filter_widgets.append(container)
        self.root.addLayout(self.filters)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("searchData")
        self.latest_button = QPushButton("Latest 100")
        self.reset_button = QPushButton("Reset")
        self.replay_button = QPushButton("Show in Kinova")
        self.replay_button.setEnabled(False)
        self.charts_button = QPushButton("Show charts")
        self.charts_button.setEnabled(False)
        self.action_buttons = (self.search_button, self.latest_button, self.reset_button,
                               self.replay_button, self.charts_button)
        for button in self.action_buttons:
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        summary = QHBoxLayout()
        self.status = QLabel("Click «Latest 100» to load records")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        summary.addWidget(self.status, 1)
        self.selected_label = QLabel("Selected: 0")
        summary.addWidget(self.selected_label)
        self.root.addLayout(summary)
        self.model = FeedbackTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(155)
        self.table.setColumnWidth(0, 38)
        self.table.setColumnWidth(1, 210)
        self.table.horizontalHeader().sectionClicked.connect(self.model.toggle_all)
        self.root.addWidget(self.table, 1)
        self.model.selection_changed.connect(lambda count: self.selected_label.setText(f"Selected: {count}"))
        self.model.selection_changed.connect(lambda count: self.replay_button.setEnabled(count > 0 and self.worker is None))
        self.model.selection_changed.connect(lambda count: self.charts_button.setEnabled(count > 0 and self.worker is None))
        self.charts_button.clicked.connect(self.send_selected_charts)
        self.replay_button.clicked.connect(self.send_selected)
        self.search_button.clicked.connect(self.search)
        self.latest_button.clicked.connect(self.load_latest)
        self.reset_button.clicked.connect(self.reset_filters)
        self.adapt_layout()

    def send_selected(self):
        rows = self.model.selected_rows()
        if rows:
            self.replay_requested.emit(rows)

    def send_selected_charts(self):
        rows = self.model.selected_rows()
        if rows:
            self.charts_requested.emit(rows)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "action_buttons"):
            self.adapt_layout()

    def minimumSizeHint(self):
        return QSize(0, 0)

    def adapt_layout(self):
        # Measure translated labels so the toolbar wraps before controls overlap.
        spacing = self.filters.horizontalSpacing()
        spacing = spacing if spacing >= 0 else 12
        required_width = (sum(widget.sizeHint().width() for widget in self.filter_widgets)
                          + sum(button.sizeHint().width() for button in self.action_buttons)
                          + spacing * 8 + 40)
        mode = "wide" if self.width() >= required_width else ("compact" if self.width() < 900 else "medium")
        if mode == self._layout_compact:
            return
        self._layout_compact = mode
        while self.filters.count():
            self.filters.takeAt(0)
        for i in range(10):
            self.filters.setColumnStretch(i, 0)
        columns = 2 if mode == "compact" else 4
        for i, widget in enumerate(self.filter_widgets):
            self.filters.addWidget(widget, i // columns, i % columns)
            self.filters.setColumnStretch(i % columns, 0 if mode == "wide" else 1)
        if mode == "wide":
            for i, button in enumerate(self.action_buttons):
                self.filters.addWidget(button, 0, i + 4, Qt.AlignmentFlag.AlignBottom)
            self.filters.setColumnStretch(9, 1)
        else:
            row = 2 if mode == "compact" else 1
            for i, button in enumerate(self.action_buttons):
                self.filters.addWidget(button, row + i // columns, i % columns,
                                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            QTimer.singleShot(0, self.load_latest)

    def search(self):
        start = QDateTime(self.from_date.date(), self.from_time.time(), DISPLAY_ZONE)
        end = QDateTime(self.to_date.date(), self.to_time.time(), DISPLAY_ZONE)
        if start > end:
            self.status.setText("Invalid interval: start must be before end")
            return
        first = datetime.fromtimestamp(start.toSecsSinceEpoch(), timezone.utc)
        # Include the selected final second with an exclusive upper query bound.
        last = datetime.fromtimestamp(end.toSecsSinceEpoch(), timezone.utc) + timedelta(seconds=1)
        self.load_rows(first, last, SEARCH_LIMIT + 1, "Search results")

    def load_latest(self):
        self.load_rows(None, None, 100, "Latest 100 records")

    def reset_filters(self):
        today = QDateTime.currentDateTime().toTimeZone(DISPLAY_ZONE).date()
        self.from_date.setDate(today)
        self.to_date.setDate(today)
        self.from_time.setTime(QTime(0, 0, 0))
        self.to_time.setTime(QTime(23, 59, 59))
        self.load_latest()

    def load_rows(self, start, end, limit, text):
        if self.worker is not None:
            return
        try:
            if self.database_config_provider is None:
                raise ValueError("Configure the PostgreSQL connection in Data Recorder")
            config = self.database_config_provider()
            self._request_text = text
            self._limit = limit
            self.worker = DataTableWorker(config, start, end, limit, self)
            self.worker.loaded.connect(self.receive_rows)
            self.worker.failed.connect(self.query_failed)
            self.worker.finished.connect(self.query_finished)
            self.set_busy(True)
            self.model.replace_rows([])
            self.status.setText("Loading records…")
            self.worker.start()
        except Exception as error:
            self.status.setText(f"Error: {error}")

    def receive_rows(self, rows):
        truncated = self._limit > 100 and len(rows) > SEARCH_LIMIT
        self.model.replace_rows(rows[:SEARCH_LIMIT])
        text = f"{self._request_text} — {self.model.rowCount()} rows"
        if truncated:
            text += " (limited to 10,000; narrow the date range)"
        self.status.setText(text)

    def query_failed(self, error):
        self.status.setText(f"PostgreSQL error: {error}")

    def query_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)

    def set_busy(self, busy):
        self.charts_button.setEnabled(not busy and bool(self.model.checked))
        self.replay_button.setEnabled(not busy and bool(self.model.checked))
        for widget in (self.search_button, self.latest_button, self.reset_button,
                       self.from_date, self.from_time, self.to_date, self.to_time):
            widget.setEnabled(not busy)
