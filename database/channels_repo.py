from __future__ import annotations

from typing import Any, Dict, List, Optional

from classifier.catalogs import CHANNEL_CATALOG, OFFICIAL_TOPICS
from config import settings
from database.logger import get_logger

logger = get_logger("database.channels")


class ChannelsRepoMixin:
    def bind_channel(
        self,
        category_key: str,
        chat_id: int,
        username: Optional[str] = None,
        invite_url: Optional[str] = None,
        pinned_msg_id: Optional[int] = None,
    ) -> bool:
        if category_key not in CHANNEL_CATALOG:
            return False
        spec = CHANNEL_CATALOG[category_key]
        now = self._now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO channels (
                        category_key, channel_name, channel_description,
                        chat_id, username, invite_url, pinned_msg_id, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(category_key) DO UPDATE SET
                        channel_name = excluded.channel_name,
                        channel_description = excluded.channel_description,
                        chat_id = excluded.chat_id,
                        username = COALESCE(excluded.username, channels.username),
                        invite_url = COALESCE(excluded.invite_url, channels.invite_url),
                        pinned_msg_id = COALESCE(excluded.pinned_msg_id, channels.pinned_msg_id),
                        updated_at = excluded.updated_at
                    """,
                    (
                        category_key,
                        spec["title"],
                        spec["description"],
                        int(chat_id),
                        username,
                        invite_url,
                        pinned_msg_id,
                        now,
                    ),
                )
                conn.commit()
                logger.info(
                    f"Canal [{category_key}] vinculado ao chat_id={chat_id} (url={invite_url or 'privado'})."
                )
                return True
            finally:
                conn.close()

    def unbind_channel(self, category_key: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    UPDATE channels
                    SET chat_id = NULL, username = NULL, invite_url = NULL,
                        pinned_msg_id = NULL, updated_at = ?
                    WHERE category_key = ?
                    """,
                    (self._now_iso(), category_key),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def set_channel_pinned_msg(self, category_key: str, pinned_msg_id: int) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE channels SET pinned_msg_id = ?, updated_at = ? WHERE category_key = ?",
                    (int(pinned_msg_id), self._now_iso(), category_key),
                )
                conn.commit()
            finally:
                conn.close()

    def get_channel(self, category_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM channels WHERE category_key = ?",
                    (category_key,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def get_channel_chat_id(self, category_key: str) -> Optional[int]:
        ch = self.get_channel(category_key)
        if ch and ch.get("chat_id") is not None:
            return int(ch["chat_id"])
        return None

    def get_hub_channel(self) -> Optional[Dict[str, Any]]:
        return self.get_channel("hub")

    def get_all_channels(self, include_hub: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                if include_hub:
                    rows = conn.execute(
                        "SELECT * FROM channels ORDER BY CASE WHEN category_key = 'hub' THEN 0 ELSE 1 END, rowid"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM channels WHERE category_key != 'hub' ORDER BY rowid"
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_linked_category_keys(self) -> List[str]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT category_key FROM channels
                    WHERE category_key != 'hub' AND chat_id IS NOT NULL
                    ORDER BY rowid
                    """
                ).fetchall()
                return [
                    str(r["category_key"])
                    for r in rows
                    if str(r["category_key"]) in OFFICIAL_TOPICS
                ]
            finally:
                conn.close()

    def set_folder_url(self, folder_url: str) -> None:
        self.set_config("telegram_folder_url", folder_url.strip())

    def get_folder_url(self) -> str:
        return (
            self.get_config("telegram_folder_url")
            or settings.telegram_folder_url
            or ""
        ).strip()

    def add_admin_user_id(self, user_id: int) -> None:
        current = set(self.get_admin_user_ids())
        current.add(int(user_id))
        self.set_config("admin_user_ids", ",".join(str(x) for x in sorted(current)))

    def get_admin_user_ids(self) -> List[int]:
        ids = set(settings.admin_user_ids)
        raw = self.get_config("admin_user_ids", "") or ""
        for part in raw.split(","):
            clean = part.strip()
            if clean.isdigit():
                ids.add(int(clean))
        return sorted(ids)
