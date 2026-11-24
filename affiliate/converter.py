from __future__ import annotations

from typing import Optional

import httpx

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
        is_monetized_ml_url,
    )

    clean_url = await unshorten_and_clean_url(raw_url, client=client)
    if not clean_url:
        return ""

    if not is_mercadolivre_url(clean_url):
        if cfg.ml_only_mode:
            return ""
        return clean_url

    is_default = cfg is settings

    short_link = await generate_short_link_via_cookie(
        clean_url, cfg=cfg, client=client
    )
    if short_link and is_monetized_ml_url(short_link):
        logger.info(f"Link curto oficial ML gerado: {short_link}")
        return short_link

    fallback_url = build_fallback_affiliate_url(
        clean_url,
        matt_tool=None if is_default else cfg.ml_matt_tool,
        matt_word=None if is_default else cfg.ml_matt_word,
    )
    if cfg.require_affiliate_link and not is_monetized_ml_url(fallback_url):
        logger.warning(
            "Link do Mercado Livre bloqueado por falta de credencial de afiliado (use /configurar_afiliado)."
        )
        return ""
    return fallback_url
