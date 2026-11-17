from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from bs4 import BeautifulSoup

from database.logger import get_logger
from scrapers.base import BaseScraper, ScrapedOffer, parse_brl_price

logger = get_logger("scrapers.pelando")

PELANDO_URLS = [
    "https://www.pelando.com.br/recentes",
    "https://www.pelando.com.br/c/tech-lover",
    "https://www.pelando.com.br/c/mundo-gamer",
    "https://www.pelando.com.br/c/para-meu-lar",
    "https://www.pelando.com.br/c/para-elas",
    "https://www.pelando.com.br/c/para-eles",
]


def _clean_pelando_title(raw_title: str) -> str:

    title = raw_title.strip()
    title = re.sub(r"^(?:\[[^\]]{1,25}\]\s*)+", "", title).strip()
    title = re.sub(r"\s*\|\s*[^|]{2,35}$", "", title).strip()
    return title


def _walk_json_for_deals(node: Any, collected: List[Dict[str, Any]]) -> None:

    if isinstance(node, dict):
        title = node.get("title")
        price = node.get("price")
        if title and price is not None and isinstance(title, str) and len(title) > 5:
            collected.append(node)
        for val in node.values():
            _walk_json_for_deals(val, collected)
    elif isinstance(node, list):
        for item in node:
            _walk_json_for_deals(item, collected)


def parse_pelando_html(html_content: str) -> List[ScrapedOffer]:
    soup = BeautifulSoup(html_content, "lxml")
    offers: List[ScrapedOffer] = []
    seen: set[str] = set()


    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            raw_deals: List[Dict[str, Any]] = []
            _walk_json_for_deals(data, raw_deals)

            for d in raw_deals:
                title = _clean_pelando_title(str(d.get("title") or ""))
                price = parse_brl_price(d.get("price"))
                if not title or not price or price <= 0:
                    continue

                source_url = (
                    d.get("sourceUrl")
                    or d.get("visitUrl")
                    or d.get("dealUrl")
                    or d.get("url")
                )
                slug = d.get("slug") or d.get("id")
                if not source_url and slug:
                    source_url = f"https://www.pelando.com.br/d/{slug}"
                if not source_url:
                    continue

                source_url = str(source_url).strip()
                if source_url.startswith("/"):
                    source_url = f"https://www.pelando.com.br{source_url}"

                if source_url in seen:
                    continue

                coupon = d.get("couponCode") or d.get("voucherCode") or d.get("coupon")
                if isinstance(coupon, dict):
                    coupon = coupon.get("code")

                img = d.get("image") or d.get("imageUrl") or d.get("mainImage")
                if isinstance(img, dict):
                    img = img.get("url") or img.get("large") or img.get("medium")

                store_name = "Mercado Livre"
                store_obj = d.get("merchant") or d.get("store")
                if isinstance(store_obj, dict) and store_obj.get("name"):
                    store_name = str(store_obj["name"])

                seen.add(source_url)
                offers.append(
                    ScrapedOffer(
                        title=title,
                        price=price,
                        coupon=str(coupon).strip() if coupon else None,
                        url=source_url,
                        image_url=str(img) if img else None,
                        store=store_name,
                        source="pelando",
                    )
                )
        except Exception as exc:
            logger.debug(f"Falha ao ler __NEXT_DATA__ do Pelando: {exc}")


    if not offers:
        for card in soup.select("li, article"):
            card_text = card.get_text(" ", strip=True)
            if "R$" not in card_text or "Expirada" in card_text:
                continue

            deal_links = card.select("a[href*='/d/']")
            if not deal_links:
                continue

            title = ""
            href = ""
            for a_el in deal_links:
                cand_href = str(a_el.get("href") or "").strip()
                cand_text = a_el.get("title") or a_el.get_text(" ", strip=True)
                cand_text = str(cand_text).strip()
                if (
                    len(cand_text) > 10
                    and "ver promoção" not in cand_text.lower()
                    and not cand_text.isdigit()
                ):
                    title = cand_text
                    href = cand_href
                    break

            if not title or not href:
                continue
            title = _clean_pelando_title(title)
            if not title:
                continue
            if href.startswith("/"):
                href = f"https://www.pelando.com.br{href}"
            if href in seen:
                continue


            stamp_el = card.select_one("[class*='deal-card-stamp']")
            price = None
            if stamp_el:
                price = parse_brl_price(stamp_el.get_text(" ", strip=True))
            if not price:
                m_price = re.search(
                    r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)", card_text
                )
                price = parse_brl_price(m_price.group(1)) if m_price else None
            if not price or price <= 1.0:
                continue

            store_name = "Loja Oficial"
            store_el = card.select_one("[class*='deal-card-store'] a")
            if store_el and store_el.get_text(strip=True):
                store_name = store_el.get_text(" ", strip=True)
            else:
                m_store = re.search(
                    r"Vendido\s+por\s+([A-Za-zÀ-ÿ0-9\s!\.&-]+?)(?:\s+R\$|\s+\d+°|\s+\||$)",
                    card_text,
                )
                if m_store:
                    store_name = m_store.group(1).strip()

            img_el = card.select_one("img[src*='pelando'], img[src*='http']")
            img_url = None
            if img_el:
                srcset = str(img_el.get("srcset") or "").strip()
                if srcset:

                    parts = [p.strip().split()[0] for p in srcset.split(",") if p.strip()]
                    if parts and parts[-1].startswith("http"):
                        img_url = parts[-1]
                if not img_url:
                    raw_src = img_el.get("src") or img_el.get("data-src")
                    if raw_src and str(raw_src).startswith("http"):
                        img_url = str(raw_src)

            seen.add(href)
            offers.append(
                ScrapedOffer(
                    title=title,
                    price=price,
                    url=href,
                    image_url=img_url,
                    store=store_name,
                    source="pelando",
                )
            )

    return offers


class PelandoScraper(BaseScraper):


    async def fetch_offers(self) -> List[ScrapedOffer]:
        all_offers: List[ScrapedOffer] = []
        seen_urls: set[str] = set()
        for url in PELANDO_URLS:
            html_text = await self.fetch_text(url)
            if html_text:
                offers = parse_pelando_html(html_text)
                for item in offers:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_offers.append(item)
        if all_offers:
            logger.info(f"[Pelando] {len(all_offers)} ofertas únicas coletadas.")
        else:
            logger.info("[Pelando] Nenhuma oferta coletada neste ciclo.")
        return all_offers
