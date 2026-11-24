from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import OFFICIAL_TOPICS, settings
from database.signatures import build_title_signature


class HistoryRepoMixin:
    def get_price_history_context(
        self, offer_key: str, price: float, title: str = ""
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "is_historical_low": False,
            "previous_low": None,
            "savings_vs_low": 0.0,
        }
        if not offer_key or price <= 0:
            return result

        sig = build_title_signature(title) if title else ""
        with self._lock:
            conn = self._connect()
            try:
                if sig:
                    row = conn.execute(
                        """
                        SELECT lowest_price, price FROM posted_offers
                        WHERE offer_key = ? OR title_signature = ?
                        ORDER BY COALESCE(lowest_price, price) ASC LIMIT 1
                        """,
                        (offer_key, sig),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT lowest_price, price FROM posted_offers WHERE offer_key = ?",
                        (offer_key,),
                    ).fetchone()
                if not row:
                    return result
                prev_low = float(row["lowest_price"] or row["price"] or 0.0)
                if 0 < price < prev_low:
                    result["is_historical_low"] = True
                    result["previous_low"] = prev_low
                    result["savings_vs_low"] = round(prev_low - price, 2)
                return result
            finally:
                conn.close()

    def is_historical_low(self, offer_key: str, price: float) -> bool:
        return bool(
            self.get_price_history_context(offer_key, price)["is_historical_low"]
        )

    def can_post_offer(
        self,
        offer_key: str,
        new_price: float,
        dedup_hours: Optional[int] = None,
        price_drop_pct: Optional[float] = None,
        title: str = "",
    ) -> bool:
        hours = dedup_hours if dedup_hours is not None else settings.dedup_hours
        drop_pct = (
            price_drop_pct
            if price_drop_pct is not None
            else settings.dedup_price_drop_pct
        )
        sig = build_title_signature(title) if title else ""

        with self._lock:
            conn = self._connect()
            try:
                if sig:
                    pending = conn.execute(
                        """
                        SELECT id, price FROM offer_queue
                        WHERE (offer_key = ? OR title_signature = ?) AND status = 'pending'
                        ORDER BY price ASC LIMIT 1
                        """,
                        (offer_key, sig),
                    ).fetchone()
                else:
                    pending = conn.execute(
                        """
                        SELECT id, price FROM offer_queue
                        WHERE offer_key = ? AND status = 'pending'
                        """,
                        (offer_key,),
                    ).fetchone()

                if pending:
                    if new_price > 0 and float(pending["price"]) > new_price:
                        return True
                    return False

                if sig:
                    row = conn.execute(
                        """
                        SELECT price, posted_at FROM posted_offers
                        WHERE offer_key = ? OR title_signature = ?
                        ORDER BY posted_at DESC LIMIT 1
                        """,
                        (offer_key, sig),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT price, posted_at FROM posted_offers
                        WHERE offer_key = ?
                        """,
                        (offer_key,),
                    ).fetchone()

                if not row:
                    return True

                old_price = float(row["price"])
                posted_at_str = row["posted_at"]
                try:
                    posted_at = datetime.fromisoformat(posted_at_str)
                    if posted_at.tzinfo is None:
                        posted_at = posted_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    return True

                now = datetime.now(timezone.utc)
                if now - posted_at >= timedelta(hours=hours):
                    return True

                if old_price > 0 and new_price > 0:
                    drop = ((old_price - new_price) / old_price) * 100.0
                    if drop >= drop_pct - 1e-6:
                        return True

                return False
            finally:
                conn.close()

    def record_posted_offer(
        self,
        offer_key: str,
        title: str,
        price: float,
        topic_key: str,
        original_price: Optional[float] = None,
        affiliate_url: Optional[str] = None,
        original_url: Optional[str] = None,
        message_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        has_photo: bool = False,
        caption_html: Optional[str] = None,
        target_chat_id: Optional[int] = None,
    ) -> None:
        sig = build_title_signature(title)
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    "SELECT lowest_price, price FROM posted_offers WHERE offer_key = ?",
                    (offer_key,),
                ).fetchone()
                lowest = float(price)
                if existing:
                    prev_low = float(
                        existing["lowest_price"] or existing["price"] or price
                    )
                    lowest = min(lowest, prev_low)

                conn.execute(
                    """
                    INSERT INTO posted_offers (
                        offer_key, title, title_signature, price, lowest_price, original_price,
                        topic_key, affiliate_url, original_url, target_chat_id, message_id,
                        thread_id, has_photo, is_expired, caption_html, posted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    ON CONFLICT(offer_key) DO UPDATE SET
                        title = excluded.title,
                        title_signature = excluded.title_signature,
                        price = excluded.price,
                        lowest_price = excluded.lowest_price,
                        original_price = excluded.original_price,
                        topic_key = excluded.topic_key,
                        affiliate_url = excluded.affiliate_url,
                        original_url = COALESCE(excluded.original_url, posted_offers.original_url),
                        target_chat_id = COALESCE(excluded.target_chat_id, posted_offers.target_chat_id),
                        message_id = COALESCE(excluded.message_id, posted_offers.message_id),
                        thread_id = COALESCE(excluded.thread_id, posted_offers.thread_id),
                        has_photo = excluded.has_photo,
                        is_expired = 0,
                        caption_html = COALESCE(excluded.caption_html, posted_offers.caption_html),
                        posted_at = excluded.posted_at
                    """,
                    (
                        offer_key,
                        title,
                        sig,
                        float(price),
                        lowest,
                        float(original_price) if original_price else None,
                        topic_key,
                        affiliate_url,
                        original_url,
                        target_chat_id,
                        message_id,
                        thread_id,
                        1 if has_photo else 0,
                        caption_html,
                        self._now_iso(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO price_history (offer_key, title_signature, title, price, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (offer_key, sig, title, float(price), self._now_iso()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_top_offers_last_24h(self, limit: int = 5) -> List[Dict[str, Any]]:
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(
            timespec="seconds"
        )
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT title, price, original_price, discount_pct, store, affiliate_url, topic_key
                    FROM offer_queue
                    WHERE status = 'sent' AND sent_at >= ?
                    ORDER BY
                        discount_pct DESC,
                        id DESC
                    LIMIT ?
                    """,
                    (cutoff_iso, limit * 2),
                ).fetchall()
                seen_sigs = set()
                results: List[Dict[str, Any]] = []
                for r in rows:
                    sig = build_title_signature(r["title"])
                    if sig in seen_sigs:
                        continue
                    seen_sigs.add(sig)
                    results.append(dict(r))
                    if len(results) >= limit:
                        break
                return results
            finally:
                conn.close()

    def get_recent_posted_for_expiration_check(
        self, hours: int = 2, limit: int = 8
    ) -> List[Dict[str, Any]]:
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(
            timespec="seconds"
        )
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT offer_key, title, price, original_price, topic_key,
                           affiliate_url, original_url, target_chat_id, message_id,
                           thread_id, has_photo, caption_html
                    FROM posted_offers
                    WHERE posted_at >= ?
                      AND message_id IS NOT NULL
                      AND COALESCE(is_expired, 0) = 0
                      AND COALESCE(original_url, affiliate_url) IS NOT NULL
                    ORDER BY
                        CASE WHEN topic_key = 'ofertas_bugs' THEN 0 ELSE 1 END ASC,
                        posted_at DESC
                    LIMIT ?
                    """,
                    (cutoff_iso, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def mark_posted_offer_expired(self, offer_key: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE posted_offers SET is_expired = 1, expired_at = ? WHERE offer_key = ?",
                    (self._now_iso(), offer_key),
                )
                conn.commit()
            finally:
                conn.close()

    def get_expired_offers_for_deletion(
        self, older_than_hours: int = 12, limit: int = 10
    ) -> List[Dict[str, Any]]:
        if older_than_hours < 0:
            return []
        cutoff_iso = (
            datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        ).isoformat(timespec="seconds")
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT offer_key, title, target_chat_id, message_id, thread_id
                    FROM posted_offers
                    WHERE COALESCE(is_expired, 0) = 1
                      AND COALESCE(is_deleted, 0) = 0
                      AND message_id IS NOT NULL
                      AND COALESCE(expired_at, posted_at) <= ?
                    ORDER BY COALESCE(expired_at, posted_at) ASC
                    LIMIT ?
                    """,
                    (cutoff_iso, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def mark_posted_offer_deleted(self, offer_key: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE posted_offers SET is_deleted = 1 WHERE offer_key = ?",
                    (offer_key,),
                )
                conn.commit()
            finally:
                conn.close()

    def record_price_point(
        self, offer_key: str, title: str, price: float
    ) -> None:
        if not offer_key or price <= 0:
            return
        sig = build_title_signature(title)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO price_history (offer_key, title_signature, title, price, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (offer_key, sig, title, float(price), self._now_iso()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_offer_price_points(
        self, query_or_key: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        q = query_or_key.strip()
        if not q:
            return []
        sig = build_title_signature(q)
        like_q = f"%{q}%"

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT title, price, recorded_at
                    FROM price_history
                    WHERE offer_key = ? OR title_signature = ? OR title LIKE ?
                    ORDER BY recorded_at ASC
                    LIMIT ?
                    """,
                    (q, sig, like_q, limit),
                ).fetchall()
                points = [dict(r) for r in rows]
                if len(points) < 2:
                    fallback_rows = conn.execute(
                        """
                        SELECT title, price, created_at AS recorded_at
                        FROM offer_queue
                        WHERE offer_key = ? OR title_signature = ? OR title LIKE ?
                        UNION ALL
                        SELECT title, price, posted_at AS recorded_at
                        FROM posted_offers
                        WHERE offer_key = ? OR title_signature = ? OR title LIKE ?
                        ORDER BY recorded_at ASC
                        LIMIT ?
                        """,
                        (q, sig, like_q, q, sig, like_q, limit),
                    ).fetchall()
                    if len(fallback_rows) > len(points):
                        points = [dict(r) for r in fallback_rows]
                return points
            finally:
                conn.close()

    def get_showcase_offers(
        self,
        topic_key: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 60,
    ) -> List[Dict[str, Any]]:
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat(
            timespec="seconds"
        )
        sql = """
            SELECT id, offer_key, title, price, original_price, discount_pct,
                   coupon, installments, store, is_full, image_url,
                   affiliate_url, topic_key, rating, reviews_count,
                   condition, seller_reputation, status, created_at
            FROM offer_queue
            WHERE status IN ('sent', 'pending')
              AND created_at >= ?
        """
        params: List[Any] = [cutoff_iso]
        if topic_key and topic_key in OFFICIAL_TOPICS:
            sql += " AND topic_key = ?"
            params.append(topic_key)
        if search_query and search_query.strip():
            sql += " AND title LIKE ?"
            params.append(f"%{search_query.strip()}%")
        sql += " ORDER BY CASE WHEN status = 'sent' THEN 0 ELSE 1 END ASC, id DESC LIMIT ?"
        params.append(int(limit))

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, tuple(params)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_24h_operational_report(self) -> Dict[str, Any]:
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(
            timespec="seconds"
        )
        with self._lock:
            conn = self._connect()
            try:
                by_source_rows = conn.execute(
                    """
                    SELECT COALESCE(source, 'ml_offers') AS src, COUNT(*) AS c
                    FROM offer_queue
                    WHERE created_at >= ?
                    GROUP BY COALESCE(source, 'ml_offers')
                    ORDER BY c DESC
                    """,
                    (cutoff_iso,),
                ).fetchall()
                by_source = {r["src"]: r["c"] for r in by_source_rows}

                sent_by_topic_rows = conn.execute(
                    """
                    SELECT topic_key, COUNT(*) AS c
                    FROM offer_queue
                    WHERE status = 'sent' AND sent_at >= ?
                    GROUP BY topic_key
                    ORDER BY c DESC
                    """,
                    (cutoff_iso,),
                ).fetchall()
                sent_by_topic = {r["topic_key"]: r["c"] for r in sent_by_topic_rows}

                sent_by_store_rows = conn.execute(
                    """
                    SELECT store, COUNT(*) AS c
                    FROM offer_queue
                    WHERE status = 'sent' AND sent_at >= ?
                    GROUP BY store
                    ORDER BY c DESC
                    """,
                    (cutoff_iso,),
                ).fetchall()
                sent_by_store = {r["store"]: r["c"] for r in sent_by_store_rows}

                expired_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM posted_offers WHERE COALESCE(is_expired, 0) = 1 AND posted_at >= ?",
                    (cutoff_iso,),
                ).fetchone()["c"]

                failed_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM offer_queue WHERE status = 'failed' AND sent_at >= ?",
                    (cutoff_iso,),
                ).fetchone()["c"]

                base_stats = self.get_stats()
                base_stats.update(
                    {
                        "24h_by_source": by_source,
                        "24h_sent_by_topic": sent_by_topic,
                        "24h_sent_by_store": sent_by_store,
                        "24h_sent_total": sum(sent_by_topic.values()),
                        "24h_expired_detected": expired_count,
                        "24h_jit_discarded": failed_count,
                    }
                )
                return base_stats
            finally:
                conn.close()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                pending_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM offer_queue WHERE status = 'pending'"
                ).fetchone()["c"]
                sent_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM posted_offers"
                ).fetchone()["c"]
                configured_topics = conn.execute(
                    "SELECT COUNT(*) AS c FROM topics WHERE thread_id IS NOT NULL"
                ).fetchone()["c"]
                total_topics = conn.execute(
                    "SELECT COUNT(*) AS c FROM topics"
                ).fetchone()["c"]
                linked_channels = conn.execute(
                    "SELECT COUNT(*) AS c FROM channels WHERE category_key != 'hub' AND chat_id IS NOT NULL"
                ).fetchone()["c"]
                total_channels = conn.execute(
                    "SELECT COUNT(*) AS c FROM channels WHERE category_key != 'hub'"
                ).fetchone()["c"]
                hub_row = conn.execute(
                    "SELECT chat_id FROM channels WHERE category_key = 'hub'"
                ).fetchone()
                hub_linked = bool(hub_row and hub_row["chat_id"] is not None)
                by_topic_rows = conn.execute(
                    """
                    SELECT topic_key, COUNT(*) AS c
                    FROM offer_queue
                    WHERE status = 'pending'
                    GROUP BY topic_key
                    """
                ).fetchall()
                by_topic = {r["topic_key"]: r["c"] for r in by_topic_rows}
                return {
                    "chat_id": self.get_chat_id(),
                    "is_paused": self.is_paused(),
                    "pending_queue": pending_count,
                    "pending_by_topic": by_topic,
                    "posted_total": sent_count,
                    "configured_topics": configured_topics,
                    "total_topics": total_topics,
                    "linked_channels": linked_channels,
                    "total_channels": total_channels,
                    "hub_linked": hub_linked,
                }
            finally:
                conn.close()
