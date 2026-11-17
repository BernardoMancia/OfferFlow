from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from classifier.catalogs import (
    BLACKLIST_NACIONAIS,
    BLOCKED_JUNK_KEYWORDS,
    HUNTER_COMIDAS_TERMS,
    HUNTER_DOCES_TERMS,
    OFFICIAL_TOPICS,
    TOPIC_EMOJIS,
    WHITELIST_MARCAS_COMIDAS,
    WHITELIST_MARCAS_DOCES,
    WHITELIST_ORIGENS,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _resolve_log_db_path(project_name: str, env_path: str) -> Path:
    if env_path and env_path.strip():
        return Path(env_path.strip())
    return BASE_DIR / "logs" / "logs.db"


@dataclass
class Settings:
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "").strip()
    )
    ml_matt_tool: str = field(
        default_factory=lambda: os.getenv("ML_MATT_TOOL", "").strip()
    )
    ml_matt_word: str = field(
        default_factory=lambda: os.getenv("ML_MATT_WORD", "").strip()
    )
    ml_affiliate_tag: str = field(
        default_factory=lambda: os.getenv("ML_AFFILIATE_TAG", "").strip()
    )
    ml_affiliate_cookie: str = field(
        default_factory=lambda: os.getenv("ML_AFFILIATE_COOKIE", "").strip()
    )
    ml_csrf_token: str = field(
        default_factory=lambda: os.getenv("ML_CSRF_TOKEN", "").strip()
    )
    amazon_affiliate_tag: str = field(
        default_factory=lambda: os.getenv("AMAZON_AFFILIATE_TAG", "").strip()
    )
    shopee_affiliate_id: str = field(
        default_factory=lambda: os.getenv("SHOPEE_AFFILIATE_ID", "").strip()
    )
    shopee_app_id: str = field(
        default_factory=lambda: os.getenv("SHOPEE_APP_ID", "").strip()
    )
    shopee_app_secret: str = field(
        default_factory=lambda: os.getenv("SHOPEE_APP_SECRET", "").strip()
    )
    magalu_store_slug: str = field(
        default_factory=lambda: os.getenv("MAGALU_STORE_SLUG", "").strip()
    )
    telegram_group_invite_url: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_GROUP_INVITE_URL", "").strip()
    )
    min_discount_pct: int = field(
        default_factory=lambda: int(os.getenv("MIN_DISCOUNT_PCT", "20"))
    )
    min_rating: float = field(
        default_factory=lambda: float(os.getenv("MIN_RATING", "4.0"))
    )
    bug_discount_pct: int = field(
        default_factory=lambda: int(os.getenv("BUG_DISCOUNT_PCT", "45"))
    )
    bug_min_price: float = field(
        default_factory=lambda: float(os.getenv("BUG_MIN_PRICE", "80"))
    )
    dedup_hours: int = field(
        default_factory=lambda: int(os.getenv("DEDUP_HOURS", "48"))
    )
    dedup_price_drop_pct: float = field(
        default_factory=lambda: float(os.getenv("DEDUP_PRICE_DROP_PCT", "10"))
    )
    delete_expired_after_hours: int = field(
        default_factory=lambda: int(os.getenv("DELETE_EXPIRED_AFTER_HOURS", "12"))
    )
    quiet_hours_start: str = field(
        default_factory=lambda: os.getenv("QUIET_HOURS_START", "23:30").strip()
    )
    quiet_hours_end: str = field(
        default_factory=lambda: os.getenv("QUIET_HOURS_END", "07:30").strip()
    )
    web_port: int = field(
        default_factory=lambda: int(os.getenv("WEB_PORT", "8080"))
    )
    web_public_url: str = field(
        default_factory=lambda: os.getenv("WEB_PUBLIC_URL", "").strip()
    )
    aggregator_interval_min: int = field(
        default_factory=lambda: int(os.getenv("AGGREGATOR_INTERVAL_MIN", "3"))
    )
    ml_offers_interval_min: int = field(
        default_factory=lambda: int(os.getenv("ML_OFFERS_INTERVAL_MIN", "5"))
    )
    ml_hunter_interval_min: int = field(
        default_factory=lambda: int(os.getenv("ML_HUNTER_INTERVAL_MIN", "4"))
    )
    publish_interval_sec: int = field(
        default_factory=lambda: int(os.getenv("PUBLISH_INTERVAL_SEC", "120"))
    )
    project_name: str = field(
        default_factory=lambda: os.getenv("PROJECT_NAME", "offerflow").strip()
    )
    db_path: Path = field(
        default_factory=lambda: Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "bot.db")))
    )
    log_db_path: Path = field(init=False)
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper().strip()
    )

    def __post_init__(self) -> None:
        raw_log_path = os.getenv("LOG_DB_PATH", "")
        self.log_db_path = _resolve_log_db_path(self.project_name, raw_log_path)
        if not self.db_path.is_absolute():
            self.db_path = (BASE_DIR / self.db_path).resolve()

    @property
    def has_valid_telegram_token(self) -> bool:
        return bool(
            self.telegram_bot_token
            and self.telegram_bot_token != "SEU_TOKEN_AQUI"
            and ":" in self.telegram_bot_token
        )

    @property
    def has_ml_cookie(self) -> bool:
        return bool(
            self.ml_affiliate_cookie
            and self.ml_affiliate_tag
            and self.ml_affiliate_tag != "SUA_TAG_DE_AFILIADO"
        )

    @property
    def has_ml_fallback(self) -> bool:
        return bool(
            self.ml_matt_tool
            and self.ml_matt_tool != "SEU_MATT_TOOL"
        )

    @property
    def has_amazon_affiliate(self) -> bool:
        return bool(
            self.amazon_affiliate_tag
            and self.amazon_affiliate_tag != "SUA_TAG_AMAZON"
        )

    @property
    def has_shopee_affiliate(self) -> bool:
        return bool(
            (self.shopee_affiliate_id and self.shopee_affiliate_id != "SEU_ID_SHOPEE")
            or (self.shopee_app_id and self.shopee_app_secret)
        )

    @property
    def has_magalu_affiliate(self) -> bool:
        return bool(
            self.magalu_store_slug
            and self.magalu_store_slug != "SUA_LOJA_MAGALU"
        )


settings = Settings()

__all__ = [
    "BASE_DIR",
    "BLACKLIST_NACIONAIS",
    "BLOCKED_JUNK_KEYWORDS",
    "HUNTER_COMIDAS_TERMS",
    "HUNTER_DOCES_TERMS",
    "OFFICIAL_TOPICS",
    "Settings",
    "TOPIC_EMOJIS",
    "WHITELIST_MARCAS_COMIDAS",
    "WHITELIST_MARCAS_DOCES",
    "WHITELIST_ORIGENS",
    "settings",
]
