from __future__ import annotations

import logging
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import BASE_DIR, settings


class SQLiteDashboardLogHandler(logging.Handler):
    def __init__(self, db_path: Optional[Path] = None) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.db_path = self._prepare_db_path(db_path or settings.log_db_path)
        self._init_schema()

    def _prepare_db_path(self, target_path: Path) -> Path:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            return target_path
        except OSError:
            fallback = BASE_DIR / "logs" / "logs.db"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback

    def _init_schema(self) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=10)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        source TEXT NOT NULL,
                        message TEXT NOT NULL,
                        raw_line TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);"
                )
                conn.commit()
            finally:
                conn.close()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone().isoformat(
                timespec="seconds"
            )
            level = record.levelname
            source = record.name
            message = record.getMessage()
            if record.exc_info:
                formatter = self.formatter or logging.Formatter()
                message = f"{message}\n{formatter.formatException(record.exc_info)}"
            raw_line = f"[{ts}] [{level}] [{source}] {message}"

            with self._lock:
                conn = sqlite3.connect(str(self.db_path), timeout=10)
                try:
                    conn.execute(
                        """
                        INSERT INTO logs (timestamp, level, source, message, raw_line)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (ts, level, source, message, raw_line),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            self.handleError(record)


_SQLITE_HANDLER: Optional[SQLiteDashboardLogHandler] = None
_CONSOLE_HANDLER: Optional[logging.StreamHandler] = None
_INIT_LOCK = threading.Lock()


def get_logger(source: str = "offerflow", db_path: Optional[Path] = None) -> logging.Logger:
    global _SQLITE_HANDLER, _CONSOLE_HANDLER

    logger = logging.getLogger(source)
    level = getattr(logging, settings.log_level, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    with _INIT_LOCK:
        if db_path is not None:
            sqlite_handler = SQLiteDashboardLogHandler(db_path=db_path)
        else:
            if _SQLITE_HANDLER is None:
                _SQLITE_HANDLER = SQLiteDashboardLogHandler()
            sqlite_handler = _SQLITE_HANDLER

        if _CONSOLE_HANDLER is None:
            if hasattr(sys.stdout, "reconfigure"):
                try:
                    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            _CONSOLE_HANDLER = logging.StreamHandler(sys.stdout)
            _CONSOLE_HANDLER.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        if not any(isinstance(h, SQLiteDashboardLogHandler) for h in logger.handlers):
            logger.addHandler(sqlite_handler)
        if not any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, SQLiteDashboardLogHandler)
            for h in logger.handlers
        ):
            logger.addHandler(_CONSOLE_HANDLER)

    return logger
