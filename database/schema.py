from __future__ import annotations

from classifier.catalogs import CHANNEL_CATALOG, OFFICIAL_TOPICS
from config import settings


class SchemaMixin:
    def init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS bot_config (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS topics (
                        topic_key TEXT PRIMARY KEY,
                        topic_name TEXT NOT NULL,
                        thread_id INTEGER,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS channels (
                        category_key TEXT PRIMARY KEY,
                        channel_name TEXT NOT NULL,
                        channel_description TEXT,
                        chat_id INTEGER,
                        username TEXT,
                        invite_url TEXT,
                        pinned_msg_id INTEGER,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS posted_offers (
                        offer_key TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        title_signature TEXT,
                        price REAL NOT NULL,
                        lowest_price REAL,
                        original_price REAL,
                        topic_key TEXT NOT NULL,
                        affiliate_url TEXT,
                        posted_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS offer_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        offer_key TEXT NOT NULL,
                        title TEXT NOT NULL,
                        title_signature TEXT,
                        price REAL NOT NULL,
                        original_price REAL,
                        discount_pct INTEGER DEFAULT 0,
                        coupon TEXT,
                        installments TEXT,
                        store TEXT NOT NULL DEFAULT 'Mercado Livre',
                        is_full INTEGER DEFAULT 0,
                        image_url TEXT,
                        affiliate_url TEXT NOT NULL,
                        original_url TEXT,
                        topic_key TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        sent_at TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_offer_queue_status
                        ON offer_queue(status, created_at);
                    CREATE INDEX IF NOT EXISTS idx_posted_offers_posted_at
                        ON posted_offers(posted_at);

                    CREATE TABLE IF NOT EXISTS user_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        keyword TEXT NOT NULL,
                        max_price REAL,
                        created_at TEXT NOT NULL,
                        UNIQUE(user_id, keyword)
                    );

                    CREATE TABLE IF NOT EXISTS price_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        offer_key TEXT NOT NULL,
                        title_signature TEXT,
                        title TEXT NOT NULL,
                        price REAL NOT NULL,
                        recorded_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_price_history_key
                        ON price_history(offer_key, recorded_at);
                    CREATE INDEX IF NOT EXISTS idx_price_history_sig
                        ON price_history(title_signature, recorded_at);
                    """
                )

                posted_cols = [
                    r["name"]
                    for r in conn.execute("PRAGMA table_info(posted_offers)").fetchall()
                ]
                if "lowest_price" not in posted_cols:
                    conn.execute(
                        "ALTER TABLE posted_offers ADD COLUMN lowest_price REAL;"
                    )
                    conn.execute(
                        "UPDATE posted_offers SET lowest_price = price WHERE lowest_price IS NULL;"
                    )
                if "title_signature" not in posted_cols:
                    conn.execute(
                        "ALTER TABLE posted_offers ADD COLUMN title_signature TEXT;"
                    )
                for col_name, col_type in (
                    ("original_url", "TEXT"),
                    ("target_chat_id", "INTEGER"),
                    ("message_id", "INTEGER"),
                    ("thread_id", "INTEGER"),
                    ("has_photo", "INTEGER DEFAULT 0"),
                    ("is_expired", "INTEGER DEFAULT 0"),
                    ("expired_at", "TEXT"),
                    ("is_deleted", "INTEGER DEFAULT 0"),
                    ("caption_html", "TEXT"),
                ):
                    if col_name not in posted_cols:
                        conn.execute(
                            f"ALTER TABLE posted_offers ADD COLUMN {col_name} {col_type};"
                        )

                queue_cols = [
                    r["name"]
                    for r in conn.execute("PRAGMA table_info(offer_queue)").fetchall()
                ]
                for col_name, col_type in (
                    ("title_signature", "TEXT"),
                    ("installments", "TEXT"),
                    ("source", "TEXT DEFAULT 'ml_offers'"),
                    ("rating", "REAL"),
                    ("reviews_count", "INTEGER"),
                    ("condition", "TEXT DEFAULT 'new'"),
                    ("seller_reputation", "TEXT"),
                ):
                    if col_name not in queue_cols:
                        conn.execute(
                            f"ALTER TABLE offer_queue ADD COLUMN {col_name} {col_type};"
                        )

                alert_cols = [
                    r["name"]
                    for r in conn.execute("PRAGMA table_info(user_alerts)").fetchall()
                ]
                if "max_price" not in alert_cols:
                    conn.execute("ALTER TABLE user_alerts ADD COLUMN max_price REAL;")

                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_posted_offers_sig ON posted_offers(title_signature);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_offer_queue_sig ON offer_queue(title_signature, status);"
                )

                now = self._now_iso()
                valid_topic_keys = tuple(OFFICIAL_TOPICS.keys())
                placeholders = ",".join("?" for _ in valid_topic_keys)
                conn.execute(
                    f"DELETE FROM topics WHERE topic_key NOT IN ({placeholders})",
                    valid_topic_keys,
                )
                for topic_key, topic_name in OFFICIAL_TOPICS.items():
                    conn.execute(
                        """
                        INSERT INTO topics (topic_key, topic_name, thread_id, updated_at)
                        VALUES (?, ?, NULL, ?)
                        ON CONFLICT(topic_key) DO UPDATE SET
                            topic_name = excluded.topic_name
                        """,
                        (topic_key, topic_name, now),
                    )

                valid_channel_keys = tuple(CHANNEL_CATALOG.keys())
                ch_placeholders = ",".join("?" for _ in valid_channel_keys)
                conn.execute(
                    f"DELETE FROM channels WHERE category_key NOT IN ({ch_placeholders})",
                    valid_channel_keys,
                )
                for cat_key, spec in CHANNEL_CATALOG.items():
                    conn.execute(
                        """
                        INSERT INTO channels (
                            category_key, channel_name, channel_description,
                            chat_id, updated_at
                        )
                        VALUES (?, ?, ?, NULL, ?)
                        ON CONFLICT(category_key) DO UPDATE SET
                            channel_name = excluded.channel_name,
                            channel_description = excluded.channel_description
                        """,
                        (cat_key, spec["title"], spec["description"], now),
                    )

                if settings.telegram_hub_channel_id:
                    try:
                        hub_cid = int(settings.telegram_hub_channel_id)
                        conn.execute(
                            "UPDATE channels SET chat_id = ? WHERE category_key = 'hub' AND chat_id IS NULL",
                            (hub_cid,),
                        )
                    except ValueError:
                        pass

                if settings.telegram_chat_id:
                    conn.execute(
                        """
                        INSERT INTO bot_config (key, value, updated_at)
                        VALUES ('chat_id', ?, ?)
                        ON CONFLICT(key) DO NOTHING
                        """,
                        (str(settings.telegram_chat_id), now),
                    )

                conn.commit()
            finally:
                conn.close()
