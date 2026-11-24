from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import OFFICIAL_TOPICS
from database.logger import get_logger
from database.signatures import build_title_signature

logger = get_logger("database.queue")


class QueueRepoMixin:
    def prune_stale_and_overflow_queue(
        self, ttl_hours: int = 6, max_per_topic: int = 25
    ) -> int:
        cutoff_iso = (
            datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        ).isoformat(timespec="seconds")
        removed = 0

        with self._lock:
            conn = self._connect()
            try:
                cur_agg = conn.execute(
                    """
                    DELETE FROM offer_queue
                    WHERE status = 'pending'
                      AND (
                          affiliate_url LIKE '%promobit.com.br%'
                          OR affiliate_url LIKE '%pelando.com.br%'
                          OR affiliate_url LIKE '%gatry.com%'
                          OR store != 'Mercado Livre'
                      )
                    """
                )
                removed += cur_agg.rowcount

                valid_keys = tuple(OFFICIAL_TOPICS.keys())
                placeholders = ",".join("?" for _ in valid_keys)
                cur_legacy = conn.execute(
                    f"DELETE FROM offer_queue WHERE status = 'pending' AND topic_key NOT IN ({placeholders})",
                    valid_keys,
                )
                removed += cur_legacy.rowcount

                cur_stale = conn.execute(
                    "DELETE FROM offer_queue WHERE status = 'pending' AND created_at < ?",
                    (cutoff_iso,),
                )
                removed += cur_stale.rowcount

                for t_key in OFFICIAL_TOPICS.keys():
                    cur_cap = conn.execute(
                        """
                        DELETE FROM offer_queue
                        WHERE status = 'pending'
                          AND topic_key = ?
                          AND id NOT IN (
                              SELECT id FROM offer_queue
                              WHERE status = 'pending' AND topic_key = ?
                              ORDER BY
                                  discount_pct DESC,
                                  id ASC
                              LIMIT ?
                          )
                        """,
                        (t_key, t_key, max_per_topic),
                    )
                    removed += cur_cap.rowcount

                if removed > 0:
                    conn.commit()
                return removed
            finally:
                conn.close()

    def enqueue_offer(
        self,
        offer_key: str,
        title: str,
        price: float,
        affiliate_url: str,
        topic_key: str,
        original_price: Optional[float] = None,
        discount_pct: int = 0,
        coupon: Optional[str] = None,
        installments: Optional[str] = None,
        store: str = "Mercado Livre",
        is_full: bool = False,
        image_url: Optional[str] = None,
        original_url: Optional[str] = None,
        source: str = "ml_offers",
        rating: Optional[float] = None,
        reviews_count: Optional[int] = None,
        condition: str = "new",
        seller_reputation: Optional[str] = None,
    ) -> Optional[int]:
        if not self.can_post_offer(offer_key, price, title=title):
            return None

        sig = build_title_signature(title)

        with self._lock:
            conn = self._connect()
            try:
                if sig:
                    dup = conn.execute(
                        """
                        SELECT id, price FROM offer_queue
                        WHERE (offer_key = ? OR title_signature = ?) AND status = 'pending'
                        ORDER BY price ASC LIMIT 1
                        """,
                        (offer_key, sig),
                    ).fetchone()
                else:
                    dup = conn.execute(
                        """
                        SELECT id, price FROM offer_queue
                        WHERE offer_key = ? AND status = 'pending'
                        """,
                        (offer_key,),
                    ).fetchone()

                if dup:
                    if float(price) < float(dup["price"]):
                        conn.execute(
                            """
                            UPDATE offer_queue
                            SET offer_key = ?, title = ?, title_signature = ?, price = ?,
                                original_price = ?, discount_pct = ?, coupon = ?, installments = ?,
                                store = ?, is_full = ?, image_url = ?, affiliate_url = ?,
                                original_url = ?, topic_key = ?, condition = ?,
                                seller_reputation = COALESCE(?, seller_reputation), created_at = ?
                            WHERE id = ?
                            """,
                            (
                                offer_key,
                                title,
                                sig,
                                float(price),
                                float(original_price) if original_price else None,
                                int(discount_pct),
                                coupon,
                                installments,
                                store,
                                1 if is_full else 0,
                                image_url,
                                affiliate_url,
                                original_url,
                                topic_key,
                                condition or "new",
                                seller_reputation,
                                self._now_iso(),
                                int(dup["id"]),
                            ),
                        )
                        conn.commit()
                        logger.info(
                            f"Duplicata na fila atualizada pelo menor preço (R$ {dup['price']:.2f} -> R$ {price:.2f}): {title}"
                        )
                    return None

                cursor = conn.execute(
                    """
                    INSERT INTO offer_queue (
                        offer_key, title, title_signature, price, original_price, discount_pct,
                        coupon, installments, store, is_full, image_url, affiliate_url,
                        original_url, topic_key, source, rating, reviews_count,
                        condition, seller_reputation, status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        offer_key,
                        title,
                        sig,
                        float(price),
                        float(original_price) if original_price else None,
                        int(discount_pct),
                        coupon,
                        installments,
                        store,
                        1 if is_full else 0,
                        image_url,
                        affiliate_url,
                        original_url,
                        topic_key,
                        source or "ml_offers",
                        float(rating) if rating else None,
                        int(reviews_count) if reviews_count else None,
                        condition or "new",
                        seller_reputation,
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
                row_id = cursor.lastrowid
            finally:
                conn.close()

        self.prune_stale_and_overflow_queue()
        return row_id

    def get_next_pending_offer(
        self, only_linked_channels: bool = False
    ) -> Optional[Dict[str, Any]]:
        self.prune_stale_and_overflow_queue()

        linked_keys = self.get_linked_category_keys()
        if only_linked_channels and linked_keys:
            topic_keys = linked_keys
        else:
            topic_keys = list(OFFICIAL_TOPICS.keys())

        last_topic = self.get_config("last_published_topic", "")
        if last_topic in topic_keys:
            start_idx = (topic_keys.index(last_topic) + 1) % len(topic_keys)
            ordered_topics = topic_keys[start_idx:] + topic_keys[:start_idx]
        else:
            ordered_topics = topic_keys

        with self._lock:
            conn = self._connect()
            try:
                for t_key in ordered_topics:
                    row = conn.execute(
                        """
                        SELECT *
                        FROM offer_queue
                        WHERE status = 'pending' AND topic_key = ?
                        ORDER BY
                            discount_pct DESC,
                            id ASC
                        LIMIT 1
                        """,
                        (t_key,),
                    ).fetchone()
                    if row:
                        return dict(row)

                if only_linked_channels and linked_keys:
                    return None

                row = conn.execute(
                    """
                    SELECT *
                    FROM offer_queue
                    WHERE status = 'pending'
                    ORDER BY
                        discount_pct DESC,
                        id ASC
                    LIMIT 1
                    """
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def list_pending_queue(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT id, title, price, discount_pct, store, topic_key
                    FROM offer_queue
                    WHERE status = 'pending'
                    ORDER BY
                        discount_pct DESC,
                        id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def remove_queue_item(self, queue_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM offer_queue WHERE id = ? AND status = 'pending'",
                    (queue_id,),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def update_queue_item_price(
        self, queue_id: int, new_price: float, original_price: Optional[float] = None
    ) -> None:
        with self._lock:
            conn = self._connect()
            try:
                if original_price and original_price > new_price > 0:
                    disc = round(((original_price - new_price) / original_price) * 100)
                    conn.execute(
                        "UPDATE offer_queue SET price = ?, original_price = ?, discount_pct = ? WHERE id = ?",
                        (float(new_price), float(original_price), int(disc), queue_id),
                    )
                else:
                    conn.execute(
                        "UPDATE offer_queue SET price = ? WHERE id = ?",
                        (float(new_price), queue_id),
                    )
                conn.commit()
            finally:
                conn.close()

    def clear_pending_queue(self, topic_key: Optional[str] = None) -> int:
        with self._lock:
            conn = self._connect()
            try:
                if topic_key:
                    cursor = conn.execute(
                        "DELETE FROM offer_queue WHERE status = 'pending' AND topic_key = ?",
                        (topic_key,),
                    )
                else:
                    cursor = conn.execute(
                        "DELETE FROM offer_queue WHERE status = 'pending'"
                    )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def mark_queue_item_sent(
        self,
        queue_id: int,
        message_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        has_photo: bool = False,
        caption_html: Optional[str] = None,
        target_chat_id: Optional[int] = None,
    ) -> None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM offer_queue WHERE id = ?", (queue_id,)
                ).fetchone()
                now = self._now_iso()
                conn.execute(
                    "UPDATE offer_queue SET status = 'sent', sent_at = ? WHERE id = ?",
                    (now, queue_id),
                )
                if row:
                    conn.execute(
                        """
                        INSERT INTO bot_config (key, value, updated_at)
                        VALUES ('last_published_topic', ?, ?)
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = excluded.updated_at
                        """,
                        (str(row["topic_key"]), now),
                    )
                    existing = conn.execute(
                        "SELECT lowest_price, price FROM posted_offers WHERE offer_key = ?",
                        (row["offer_key"],),
                    ).fetchone()
                    lowest = float(row["price"])
                    if existing:
                        prev_low = float(
                            existing["lowest_price"] or existing["price"] or lowest
                        )
                        lowest = min(lowest, prev_low)

                    sig = row["title_signature"] or build_title_signature(row["title"])
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
                            row["offer_key"],
                            row["title"],
                            sig,
                            row["price"],
                            lowest,
                            row["original_price"],
                            row["topic_key"],
                            row["affiliate_url"],
                            row["original_url"],
                            target_chat_id,
                            message_id,
                            thread_id,
                            1 if has_photo else 0,
                            caption_html,
                            now,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    def mark_queue_item_failed(self, queue_id: int) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE offer_queue SET status = 'failed', sent_at = ? WHERE id = ?",
                    (self._now_iso(), queue_id),
                )
                conn.commit()
            finally:
                conn.close()
