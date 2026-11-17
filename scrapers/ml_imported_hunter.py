from __future__ import annotations

import asyncio
from typing import List, Optional
from urllib.parse import quote_plus

from classifier.imported_filter import evaluate_imported_food
from config import HUNTER_COMIDAS_TERMS, HUNTER_DOCES_TERMS
from database.db import DatabaseManager, db
from database.logger import get_logger
from scrapers.base import BaseScraper, ScrapedOffer
from scrapers.ml_offers import parse_ml_cards
from scrapers.pelando import parse_pelando_html

logger = get_logger("scrapers.ml_imported_hunter")

ML_GASTRONOMIC_CORRIDORS = [
    "https://www.mercadolivre.com.br/supermercado/market/mercearia",
    "https://www.mercadolivre.com.br/supermercado/market/bebidas-alcoolicas",
    "https://www.mercadolivre.com.br/supermercado/market/bebidas-nao-alcoolicas",
    "https://www.mercadolivre.com.br/ofertas/supermercado",
]

PELANDO_SWEETS_AND_GOURMET_QUERIES = [
    "milka",
    "lindt",
    "nutella",
    "biscoff",
    "chocolate",
    "biscoito",
    "doce",
    "havanna",
    "pringles",
    "lamen",
    "azeite",
    "cafe",
    "ferrero",
    "kinder",
    "toblerone",
    "haribo",
    "barilla",
    "samyang",
    "vinho",
    "whisky",
]


def build_circular_hunter_terms() -> List[str]:
\
\
\

    combined: List[str] = []
    max_len = max(len(HUNTER_DOCES_TERMS), len(HUNTER_COMIDAS_TERMS))
    for i in range(max_len):
        if i < len(HUNTER_DOCES_TERMS):
            combined.append(HUNTER_DOCES_TERMS[i])
        if i < len(HUNTER_COMIDAS_TERMS):
            combined.append(HUNTER_COMIDAS_TERMS[i])
    return combined


class MercadoLivreImportedHunter(BaseScraper):
\
\
\
\
\


    def __init__(
        self,
        database: DatabaseManager = db,
        terms_per_cycle: int = 4,
        min_discount_pct: int = 10,
    ) -> None:
        super().__init__()
        self.database = database
        self.terms_per_cycle = terms_per_cycle
        self.min_discount_pct = min_discount_pct
        self.terms_queue = build_circular_hunter_terms()

    def get_next_terms_batch(self, batch_size: Optional[int] = None) -> List[str]:
        size = batch_size or self.terms_per_cycle
        total = len(self.terms_queue)
        if total == 0:
            return []

        raw_cursor = self.database.get_config("hunter_cursor", "0")
        try:
            cursor = int(raw_cursor or "0") % total
        except ValueError:
            cursor = 0

        selected = [self.terms_queue[(cursor + i) % total] for i in range(size)]
        new_cursor = (cursor + size) % total
        self.database.set_config("hunter_cursor", str(new_cursor))
        return selected

    def get_next_pelando_gourmet_queries(self, count: int = 3) -> List[str]:
        total = len(PELANDO_SWEETS_AND_GOURMET_QUERIES)
        raw_cursor = self.database.get_config("hunter_pelando_cursor", "0")
        try:
            cursor = int(raw_cursor or "0") % total
        except ValueError:
            cursor = 0
        selected = [
            PELANDO_SWEETS_AND_GOURMET_QUERIES[(cursor + i) % total]
            for i in range(count)
        ]
        self.database.set_config("hunter_pelando_cursor", str((cursor + count) % total))
        return selected

    @staticmethod
    def build_search_url(term: str) -> str:
        slug = term.strip().lower().replace(" ", "-")
        encoded = quote_plus(slug)
        return f"https://lista.mercadolivre.com.br/{encoded}_NoIndex_True"

    async def hunt_offers(
        self, batch_size: Optional[int] = None
    ) -> List[ScrapedOffer]:
        terms = self.get_next_terms_batch(batch_size=batch_size)
        pelando_queries = self.get_next_pelando_gourmet_queries(count=3)
        logger.info(
            f"[Frente C - Caçador de Importados] Termos ML: {terms} | Buscas Doces/Gourmet: {pelando_queries}"
        )

        approved_offers: List[ScrapedOffer] = []
        seen_urls: set[str] = set()


        for q in pelando_queries:
            p_url = f"https://www.pelando.com.br/busca/{quote_plus(q)}"
            p_html = await self.fetch_text(p_url)
            if p_html:
                p_items = parse_pelando_html(p_html)
                for offer in p_items:
                    clean_key = offer.url.split("?")[0].split("#")[0]
                    if clean_key in seen_urls:
                        continue
                    filter_res = evaluate_imported_food(offer.title)
                    if not filter_res.approved:
                        continue
                    seen_urls.add(clean_key)
                    approved_offers.append(offer)
            await asyncio.sleep(0.3)


        search_urls = [self.build_search_url(t) for t in terms]
        ml_search_blocked = False

        for url in search_urls:
            if ml_search_blocked:
                break
            html_text = await self.fetch_text(url)
            if not html_text:
                continue
            if "suspicious-traffic" in html_text or "account-verification" in html_text:
                ml_search_blocked = True
                logger.debug(
                    "Busca lista.mercadolivre.com.br exigiu verificação de conta; priorizando corredores gastronômicos SSR."
                )
                break

            cards = parse_ml_cards(
                html_text,
                source_name="ml_hunter",
                require_previous_price=True,
                min_discount_pct=self.min_discount_pct,
            )
            for offer in cards:
                clean_key = offer.url.split("?")[0].split("#")[0]
                if clean_key in seen_urls:
                    continue
                filter_res = evaluate_imported_food(offer.title)
                if not filter_res.approved:
                    continue
                seen_urls.add(clean_key)
                approved_offers.append(offer)
            await asyncio.sleep(0.3)

        for url in ML_GASTRONOMIC_CORRIDORS:
            html_text = await self.fetch_text(url)
            if not html_text:
                continue

            cards = parse_ml_cards(
                html_text,
                source_name="ml_hunter",
                require_previous_price=True,
                min_discount_pct=self.min_discount_pct,
            )

            for offer in cards:
                clean_key = offer.url.split("?")[0].split("#")[0]
                if clean_key in seen_urls:
                    continue


                filter_res = evaluate_imported_food(offer.title)
                if not filter_res.approved:
                    continue

                seen_urls.add(clean_key)
                approved_offers.append(offer)

            await asyncio.sleep(0.3)

        logger.info(
            f"[Frente C - Caçador de Importados] {len(approved_offers)} ofertas 100% importadas aprovadas."
        )
        return approved_offers
