"""Bounded, read-only PostgreSQL queries performed outside the UI thread."""
import psycopg
from psycopg import sql
from PySide6.QtCore import QThread, Signal
from view.data_recorder_page.recording_worker import COLUMNS

SEARCH_LIMIT = 10000


def build_select(table, start=None, end=None, limit=100):
    parts = table.strip().split(".")
    if len(parts) not in (1, 2) or any(not part for part in parts):
        raise ValueError("Enter table or schema.table in Data Recorder")
    query = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(sql.Identifier(column) for column in COLUMNS),
        sql.Identifier(*parts),
    )
    params = []
    if start is not None and end is not None:
        query += sql.SQL(" WHERE {} >= %s AND {} < %s").format(
            sql.Identifier("time"), sql.Identifier("time"))
        params.extend((start, end))
    query += sql.SQL(" ORDER BY {} DESC LIMIT %s").format(sql.Identifier("time"))
    params.append(limit)
    return query, params


class DataTableWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, config, start=None, end=None, limit=100, parent=None):
        super().__init__(parent)
        self.config, self.start_time, self.end_time, self.limit = config, start, end, limit

    def run(self):
        try:
            query, params = build_select(self.config["table"], self.start_time, self.end_time, self.limit)
            with psycopg.connect(**self.config["database"], connect_timeout=5,
                                 options="-c statement_timeout=10000") as connection:
                connection.read_only = True
                rows = connection.execute(query, params).fetchall()
            self.loaded.emit(rows)
        except Exception as error:
            self.failed.emit(str(error))
