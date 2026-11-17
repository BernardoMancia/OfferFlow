from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from affiliate.url_cleaner import clean_store_url
from config import settings
from database.db import db


def _resolve_setting(
    explicit_val: Optional[str], cfg_val: str, db_key: str, is_default_cfg: bool
) -> str:
    if explicit_val is not None:
        return explicit_val.strip()
    if is_default_cfg:
        db_override = db.get_config(db_key)
        if db_override and db_override.strip():
            return db_override.strip()
    return (cfg_val or "").strip()


def build_amazon_affiliate_url(
    clean_url: str,
    amazon_tag: Optional[str] = None,
) -> str:
    normalized = clean_store_url(clean_url)
    if not normalized:
        return clean_url

    tag = _resolve_setting(
        amazon_tag, settings.amazon_affiliate_tag, "amazon_affiliate_tag", amazon_tag is None
    )
    if not tag or tag == "SUA_TAG_AMAZON":
        return normalized

    parsed = urlparse(normalized)
    if "amazon." not in parsed.netloc.lower():
        return normalized

    qs = parse_qs(parsed.query, keep_blank_values=False)
    qs["tag"] = [tag]
    new_query = urlencode(qs, doseq=True)
    return urlunparse(
        (parsed.scheme or "https", parsed.netloc, parsed.path, "", new_query, "")
    )
