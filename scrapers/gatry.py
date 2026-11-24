from __future__ import annotations

import re
from typing import List
from bs4 import BeautifulSoup

from database.logger import get_logger
from scrapers.base import BaseScraper, ScrapedOffer, parse_brl_price

logger = get_logger("scrapers.gatry")

GATRY_URL = "https://gatry.com/"


def parse_gatry_html(html_content: str) -> List[ScrapedOffer]:
    soup = BeautifulSoup(html_content, "lxml")
    offers: List[ScrapedOffer] = []
    seen: set[str] = set()

    blocks = soup.select("article.promocao, div.promocao, section.promotions article, article")
    for block in blocks:
        title_link = (
            block.select_one(".description h3 a[href]")
            or block.select_one("h3 a[href]")
            or block.select_one(".informacoes a[href]")
            or block.select_one("a.ir-loja[href]")
        )
        if not title_link:
            continue

        title = title_link.get_text(" ", strip=True)
        href = str(title_link.get("href") or "").strip()


        store_btn = block.select_one(
            ".option-store a[href*='http'], a.ir-loja[href], a.mais[href*='http']"
        )
        if store_btn and store_btn.get("href"):
            btn_href = str(store_btn.get("href")).strip()
            if btn_href.startswith("http") and "gatry.com" not in btn_href:
                href = btn_href

        if not title or not href or href in seen:
            continue

        price_el = block.select_one("p.price, .preco, [itemprop='price'], .price")
        price_raw = (
            price_el.get_text(" ", strip=True)
            if price_el
            else block.get_text(" ", strip=True)
        )
        price = parse_brl_price(price_raw)
        if not price or price <= 0:
            continue


        coupon = None
        comment_el = block.select_one("p.comment, .comentario, .description")
        if comment_el:
            comment_text = comment_el.get_text(" ", strip=True)
            m_cupom = re.search(
                r"(?:cupom|código|codigo|use)\s*[:\-]?\s*([A-Z0-9]{4,20})\b",
                comment_text,
                flags=re.IGNORECASE,
            )
            if m_cupom:
                candidate = m_cupom.group(1).upper()
                if candidate not in ("PARA", "LOJA", "AQUI", "MAIS", "PELO", "APP", "SAIR"):
                    coupon = candidate

        img_el = block.select_one(".image img, .imagem img, img[itemprop='image'], img")
        img_url = None
        if img_el:
            raw_img = img_el.get("src") or img_el.get("data-src")
            if raw_img and str(raw_img).startswith("http"):
                img_url = str(raw_img)

        seen.add(href)
        offers.append(
            ScrapedOffer(
                title=title,
                price=price,
                coupon=coupon,
                url=href,
                image_url=img_url,
                source="gatry",
            )
        )

    return offers


class GatryScraper(BaseScraper):


    async def fetch_offers(self) -> List[ScrapedOffer]:
        html_text = await self.fetch_text(GATRY_URL)
        if not html_text:
            logger.info("[Gatry] Nenhuma resposta obtida neste ciclo.")
            return []
        offers = parse_gatry_html(html_text)
        logger.info(f"[Gatry] {len(offers)} promoções coletadas.")
        return offers
