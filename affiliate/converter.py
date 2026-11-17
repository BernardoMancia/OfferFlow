from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

import httpx

from affiliate.amazon import build_amazon_affiliate_url
from affiliate.magalu import build_magalu_affiliate_url
from affiliate.shopee import build_shopee_affiliate_url, generate_shopee_short_link
from affiliate.url_cleaner import is_mercadolivre_url, unshorten_and_clean_url
from config import Settings, settings
from database.logger import get_logger

logger = get_logger("affiliate.converter")


async def convert_to_affiliate_url(
    raw_url: str,
    cfg: Settings = settings,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    from affiliate.mercadolivre import (
        build_fallback_affiliate_url,
        generate_short_link_via_cookie,
    )

    clean_url = await unshorten_and_clean_url(raw_url, client=client)
    if not clean_url:
        return raw_url

    host = urlparse(clean_url).netloc.lower()
    is_default = cfg is settings

    if "amazon." in host:
        amz_tag = None if is_default else cfg.amazon_affiliate_tag
        return build_amazon_affiliate_url(clean_url, amazon_tag=amz_tag)

    if "shopee." in host:
        short_shopee = await generate_shopee_short_link(clean_url, cfg=cfg, client=client)
        if short_shopee:
            return short_shopee
        sh_id = None if is_default else cfg.shopee_affiliate_id
        return build_shopee_affiliate_url(clean_url, shopee_id=sh_id)

    if "magazineluiza.com.br" in host or "magazinevoce.com.br" in host:
        mg_slug = None if is_default else cfg.magalu_store_slug
        return build_magalu_affiliate_url(clean_url, magalu_slug=mg_slug)

    if not is_mercadolivre_url(clean_url):
        return clean_url

    short_link = await generate_short_link_via_cookie(
        clean_url, cfg=cfg, client=client
    )
    if short_link:
        logger.info(f"Link curto oficial ML gerado: {short_link}")
        return short_link

    fallback_url = build_fallback_affiliate_url(
        clean_url,
        matt_tool=None if is_default else cfg.ml_matt_tool,
        matt_word=None if is_default else cfg.ml_matt_word,
    )
    return fallback_url
