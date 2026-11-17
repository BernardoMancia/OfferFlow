from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from affiliate.amazon import _resolve_setting, build_amazon_affiliate_url
from affiliate.converter import convert_to_affiliate_url
from affiliate.magalu import build_magalu_affiliate_url
from affiliate.shopee import (
    SHOPEE_GRAPHQL_API,
    build_shopee_affiliate_url,
    generate_shopee_short_link,
)
from affiliate.url_cleaner import clean_store_url
from config import Settings, settings
from database.db import db
from database.logger import get_logger

logger = get_logger("affiliate.mercadolivre")

ML_LINKBUILDER_API = (
    "https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink"
)


def _extract_csrf_from_cookie(cookie_str: str) -> str:
    match = re.search(
        r"(?:_csrf|csrf[_-]?token)=([^;\s]+)", cookie_str, flags=re.IGNORECASE
    )
    return match.group(1) if match else ""


def build_fallback_affiliate_url(
    clean_url: str,
    matt_tool: Optional[str] = None,
    matt_word: Optional[str] = None,
) -> str:
    normalized = clean_store_url(clean_url)
    if not normalized:
        return clean_url

    tool = _resolve_setting(matt_tool, settings.ml_matt_tool, "ml_matt_tool", matt_tool is None)
    word = _resolve_setting(matt_word, settings.ml_matt_word, "ml_matt_word", matt_word is None)

    if not tool or tool == "SEU_MATT_TOOL":
        return normalized

    params = {"matt_tool": tool}
    if word and word != "SEU_MATT_WORD":
        params["matt_word"] = word

    parsed = urlparse(normalized)
    query_str = urlencode(params)
    return urlunparse(
        (parsed.scheme or "https", parsed.netloc, parsed.path, "", query_str, "")
    )


async def generate_short_link_via_cookie(
    clean_url: str,
    cfg: Settings = settings,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[str]:
    is_default = cfg is settings
    cookie_val = _resolve_setting(None, cfg.ml_affiliate_cookie, "ml_affiliate_cookie", is_default)
    tag_val = _resolve_setting(None, cfg.ml_affiliate_tag, "ml_affiliate_tag", is_default)
    csrf_val = _resolve_setting(None, cfg.ml_csrf_token, "ml_csrf_token", is_default)

    if not cookie_val or not tag_val or tag_val == "SUA_TAG_DE_AFILIADO":
        return None

    csrf_token = csrf_val or _extract_csrf_from_cookie(cookie_val)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.mercadolivre.com.br",
        "Referer": "https://www.mercadolivre.com.br/afiliados/linkbuilder",
        "Cookie": cookie_val,
    }
    if csrf_token:
        headers["x-csrf-token"] = csrf_token

    payload = {
        "urls": [clean_url],
        "tag": tag_val,
    }

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await http_client.post(ML_LINKBUILDER_API, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            data = resp.json()
            if isinstance(data, dict):
                if "short_url" in data and data["short_url"]:
                    db.set_config("ml_cookie_expired_pending", "0")
                    return str(data["short_url"])
                urls_list = data.get("urls") or data.get("links") or []
                if isinstance(urls_list, list) and urls_list:
                    first = urls_list[0]
                    if isinstance(first, dict):
                        short = (
                            first.get("short_url")
                            or first.get("shortUrl")
                            or first.get("url")
                        )
                        if short and ("/sec/" in short or "meli.la" in short):
                            db.set_config("ml_cookie_expired_pending", "0")
                            return str(short)

        logger.warning(
            f"Linkbuilder API retornou HTTP {resp.status_code}. Ativando fallback matt_tool/matt_word."
        )
        db.set_config("ml_cookie_expired_pending", "1")
        return None
    except Exception as exc:
        logger.warning(
            f"Falha silenciosa no Linkbuilder (/sec/): {exc}. Ativando fallback matt_tool/matt_word."
        )
        db.set_config("ml_cookie_expired_pending", "1")
        return None
    finally:
        if owns_client:
            await http_client.aclose()


def consume_ml_cookie_expired_alert() -> bool:
    if db.get_config("ml_cookie_expired_pending", "0") == "1":
        db.set_config("ml_cookie_expired_pending", "0")
        return True
    return False


__all__ = [
    "ML_LINKBUILDER_API",
    "SHOPEE_GRAPHQL_API",
    "build_amazon_affiliate_url",
    "build_fallback_affiliate_url",
    "build_magalu_affiliate_url",
    "build_shopee_affiliate_url",
    "consume_ml_cookie_expired_alert",
    "convert_to_affiliate_url",
    "generate_shopee_short_link",
    "generate_short_link_via_cookie",
]
