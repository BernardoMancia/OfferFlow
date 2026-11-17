from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from bs4 import BeautifulSoup

from database.logger import get_logger
from scrapers.base import BaseScraper, ScrapedOffer, parse_brl_price

logger = get_logger("scrapers.promobit")

PROMOBIT_URLS = [
    "https://www.promobit.com.br/",
    "https://www.promobit.com.br/promocoes/recentes/",
]


def _extract_promobit_offers_from_json(
    node: Any, collected: List[Dict[str, Any]]
) -> None:
    if isinstance(node, dict):
        title = (
            node.get("offerTitle")
            or node.get("offer_title")
            or node.get("title")
        )
        price = (
            node.get("offerPrice")
            or node.get("offer_price")
            or node.get("price")
        )
        if title and price is not None and isinstance(title, str) and len(title) > 5:
            collected.append(node)
        for v in node.values():
            _extract_promobit_offers_from_json(v, collected)
    elif isinstance(node, list):
        for item in node:
            _extract_promobit_offers_from_json(item, collected)


def parse_promobit_html(html_content: str) -> List[ScrapedOffer]:
    soup = BeautifulSoup(html_content, "lxml")
    offers: List[ScrapedOffer] = []
    seen: set[str] = set()

    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            raw_items: List[Dict[str, Any]] = []
            _extract_promobit_offers_from_json(data, raw_items)

            for item in raw_items:

                if item.get("offerPriceType") == "STARTING_AT":
                    continue
                status_name = str(item.get("offerStatusName") or "").upper()
                if "EXPIRED" in status_name or "INACTIVE" in status_name:
                    continue

                title = str(
                    item.get("offerTitle")
                    or item.get("offer_title")
                    or item.get("title")
                    or ""
                ).strip()
                price = parse_brl_price(
                    item.get("offerPrice")
                    or item.get("offer_price")
                    or item.get("price")
                )
                if not title or not price or price <= 0.5:
                    continue

                raw_old = (
                    item.get("offerOldPrice")
                    or item.get("offer_old_price")
                    or item.get("oldPrice")
                    or item.get("original_price")
                )
                old_price = parse_brl_price(raw_old)
                if old_price and old_price <= price:
                    old_price = None

                disc_pct = int(float(item.get("offerDiscontPercentage") or 0))

                offer_id = item.get("offerId") or item.get("offer_id")
                slug = item.get("offerSlug") or item.get("offer_slug") or item.get("slug")

                if offer_id:
                    out_url = f"https://www.promobit.com.br/Redirect/to/{offer_id}/"
                else:
                    out_url = (
                        item.get("offer_url")
                        or item.get("store_url")
                        or item.get("url")
                        or (
                            f"https://www.promobit.com.br/oferta/{slug}"
                            if slug
                            else None
                        )
                    )
                if not out_url:
                    continue

                out_url = str(out_url).strip()
                if out_url.startswith("/"):
                    out_url = f"https://www.promobit.com.br{out_url}"
                if out_url in seen:
                    continue

                coupon = (
                    item.get("offerCoupon")
                    or item.get("offer_coupon")
                    or item.get("coupon")
                    or item.get("coupon_code")
                )
                img = (
                    item.get("offerPhoto")
                    or item.get("offer_photo")
                    or item.get("photo")
                    or item.get("image")
                )
                if isinstance(img, str):
                    if img.startswith("//"):
                        img = f"https:{img}"
                    elif img.startswith("/"):
                        img = f"https://i.promobit.com.br/268{img}"

                store = str(
                    item.get("storeName")
                    or item.get("store_name")
                    or item.get("store")
                    or "Mercado Livre"
                )

                seen.add(out_url)
                offers.append(
                    ScrapedOffer(
                        title=title,
                        price=price,
                        original_price=old_price,
                        discount_pct=disc_pct,
                        coupon=str(coupon).strip() if coupon else None,
                        url=out_url,
                        image_url=str(img) if img else None,
                        store=store,
                        source="promobit",
                    )
                )
        except Exception as exc:
            logger.debug(f"Falha ao ler __NEXT_DATA__ do Promobit: {exc}")

    return offers


class PromobitScraper(BaseScraper):


    async def fetch_offers(self) -> List[ScrapedOffer]:
        for url in PROMOBIT_URLS:
            html_text = await self.fetch_text(url)
            if html_text:
                offers = parse_promobit_html(html_text)
                if offers:
                    logger.info(f"[Promobit] {len(offers)} ofertas coletadas.")
                    return offers
        logger.info("[Promobit] Nenhuma oferta coletada neste ciclo.")
        return []
