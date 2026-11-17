from __future__ import annotations

import hashlib
import json
import time
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from affiliate.amazon import _resolve_setting
from affiliate.url_cleaner import clean_store_url
from config import Settings, settings
from database.logger import get_logger

logger = get_logger("affiliate.shopee")

SHOPEE_GRAPHQL_API = "https://open-api.affiliate.shopee.com.br/graphql"


def build_shopee_affiliate_url(
    clean_url: str,
    shopee_id: Optional[str] = None,
) -> str:
    normalized = clean_store_url(clean_url)
    if not normalized:
        return clean_url

    aff_id = _resolve_setting(
        shopee_id, settings.shopee_affiliate_id, "shopee_affiliate_id", shopee_id is None
    )
    if not aff_id or aff_id == "SEU_ID_SHOPEE":
        return normalized

    parsed = urlparse(normalized)
    if "shopee." not in parsed.netloc.lower():
        return normalized

    pid = aff_id if aff_id.startswith("an_") else f"an_{aff_id}"
    params = {
        "mmp_pid": pid,
        "utm_source": pid,
        "utm_medium": "affiliates",
    }
    return urlunparse(
        (parsed.scheme or "https", parsed.netloc, parsed.path, "", urlencode(params), "")
    )


async def generate_shopee_short_link(
    clean_url: str,
    cfg: Settings = settings,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[str]:
    is_default = cfg is settings
    app_id = _resolve_setting(None, cfg.shopee_app_id, "shopee_app_id", is_default)
    app_secret = _resolve_setting(None, cfg.shopee_app_secret, "shopee_app_secret", is_default)
    if not app_id or not app_secret:
        return None

    timestamp = int(time.time())
    query = f'mutation {{ generateShortLink(input: {{ originUrl: "{clean_url}" }}) {{ shortLink }} }}'
    payload_str = json.dumps({"query": query}, separators=(",", ":"))
    signature = hashlib.sha256(
        f"{app_id}{timestamp}{payload_str}{app_secret}".encode("utf-8")
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={signature}",
    }

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=8.0)
    try:
        resp = await http_client.post(SHOPEE_GRAPHQL_API, content=payload_str, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            short_link = (
                data.get("data", {})
                .get("generateShortLink", {})
                .get("shortLink")
            )
            if short_link:
                return str(short_link)
        return None
    except Exception as exc:
        logger.debug(f"Falha ao gerar shortLink Shopee via GraphQL: {exc}")
        return None
    finally:
        if owns_client:
            await http_client.aclose()
