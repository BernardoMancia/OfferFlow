from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from database.alerts_repo import AlertsRepoMixin
from database.channels_repo import ChannelsRepoMixin
from database.history_repo import HistoryRepoMixin
from database.logger import get_logger
from database.queue_repo import QueueRepoMixin
from database.schema import SchemaMixin
from database.signatures import _SIG_STOPWORDS, build_title_signature

logger = get_logger("database.db")


class DatabaseManager(
    SchemaMixin,
    ChannelsRepoMixin,
    QueueRepoMixin,
    HistoryRepoMixin,
    AlertsRepoMixin,
):
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or settings.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def set_config(self, key: str, value: Any) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO bot_config (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, str(value), self._now_iso()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT value FROM bot_config WHERE key = ?", (key,)
                ).fetchone()
                return row["value"] if row else default
            finally:
                conn.close()

    def set_chat_id(self, chat_id: int | str) -> None:
        self.set_config("chat_id", str(chat_id))
        logger.info(f"chat_id salvo em bot_config: {chat_id}")

    def get_chat_id(self) -> Optional[int]:
        raw = self.get_config("chat_id") or settings.telegram_chat_id
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def is_paused(self) -> bool:
        return self.get_config("is_paused", "0") == "1"

    def set_paused(self, paused: bool) -> None:
        self.set_config("is_paused", "1" if paused else "0")

    def get_all_topics(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT topic_key, topic_name, thread_id, updated_at FROM topics ORDER BY rowid"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_pending_topics(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT topic_key, topic_name, thread_id
                    FROM topics
                    WHERE thread_id IS NULL
                    ORDER BY rowid
                    """
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def set_topic_thread_id(self, topic_key: str, thread_id: Optional[int]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE topics
                    SET thread_id = ?, updated_at = ?
                    WHERE topic_key = ?
                    """,
                    (thread_id, self._now_iso(), topic_key),
                )
                conn.commit()
            finally:
                conn.close()

    def get_topic_thread_id(self, topic_key: str) -> Optional[int]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT thread_id FROM topics WHERE topic_key = ?", (topic_key,)
                ).fetchone()
                if row and row["thread_id"] is not None:
                    return int(row["thread_id"])
                return None
            finally:
                conn.close()

    def reset_topics(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE topics SET thread_id = NULL, updated_at = ?",
                    (self._now_iso(),),
                )
                conn.commit()
            finally:
                conn.close()


db = DatabaseManager()

__all__ = ["DatabaseManager", "_SIG_STOPWORDS", "build_title_signature", "db"]
