from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional


class AlertsRepoMixin:
    def add_user_alert(
        self,
        user_id: int,
        keyword: str,
        max_price: Optional[float] = None,
        chat_id: Optional[int] = None,
    ) -> Optional[int]:
        clean_kw = keyword.strip().lower()
        if len(clean_kw) < 2 or len(clean_kw) > 60:
            return None
        target_chat_id = int(chat_id) if chat_id is not None else int(user_id)
        with self._lock:
            conn = self._connect()
            try:
                count_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM user_alerts WHERE user_id = ?",
                    (int(user_id),),
                ).fetchone()
                if count_row and int(count_row["c"]) >= 15:
                    return None
                cur = conn.execute(
                    """
                    INSERT INTO user_alerts (user_id, chat_id, keyword, max_price, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, keyword) DO UPDATE SET
                        chat_id = excluded.chat_id,
                        max_price = excluded.max_price,
                        created_at = excluded.created_at
                    """,
                    (
                        int(user_id),
                        target_chat_id,
                        clean_kw,
                        float(max_price) if max_price else None,
                        self._now_iso(),
                    ),
                )
                conn.commit()
                return cur.lastrowid or 1
            finally:
                conn.close()

    def list_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id, keyword, max_price, created_at FROM user_alerts WHERE user_id = ? ORDER BY id ASC",
                    (int(user_id),),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def remove_user_alert(self, user_id: int, id_or_keyword: int | str) -> bool:
        target = str(id_or_keyword).strip().lower()
        with self._lock:
            conn = self._connect()
            try:
                if target.isdigit():
                    cur = conn.execute(
                        "DELETE FROM user_alerts WHERE user_id = ? AND id = ?",
                        (int(user_id), int(target)),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM user_alerts WHERE user_id = ? AND keyword = ?",
                        (int(user_id), target),
                    )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def match_user_alerts(
        self, title: str, price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        if not title:
            return []
        nfkd_t = unicodedata.normalize("NFKD", title.lower())
        norm_title = "".join(c for c in nfkd_t if not unicodedata.combining(c))

        with self._lock:
            conn = self._connect()
            try:
                all_alerts = conn.execute(
                    "SELECT id, user_id, chat_id, keyword, max_price FROM user_alerts"
                ).fetchall()
            finally:
                conn.close()

        matched: List[Dict[str, Any]] = []
        seen_users: set[int] = set()
        for row in all_alerts:
            uid = int(row["user_id"])
            if uid in seen_users:
                continue
            max_p = row["max_price"]
            if max_p is not None and price is not None and float(price) > float(max_p):
                continue
            kw_raw = str(row["keyword"] or "")
            nfkd_k = unicodedata.normalize("NFKD", kw_raw.lower())
            norm_kw = "".join(c for c in nfkd_k if not unicodedata.combining(c)).strip()
            if not norm_kw:
                continue
            words = [w for w in re.split(r"\s+", norm_kw) if w]
            if words and all(
                re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", norm_title)
                for w in words
            ):
                seen_users.add(uid)
                matched.append(dict(row))

        return matched
