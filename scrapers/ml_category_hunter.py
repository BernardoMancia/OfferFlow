from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from classifier.catalogs import ML_CATEGORY_HUNTER_ROUTES
from classifier.ml_compliance import evaluate_ml_compliance
from database.db import DatabaseManager, db
from database.logger import get_logger
from scrapers.base import BaseScraper, ScrapedOffer
from scrapers.ml_offers import parse_ml_cards

logger = get_logger("scrapers.ml_category_hunter")


class MercadoLivreCategoryHunter(BaseScraper):
    def __init__(
        self,
        database: DatabaseManager = db,
        routes_per_cycle: int = 4,
        min_discount_pct: int = 12,
    ) -> None:
        super().__init__()
        self.database = database
        self.routes_per_cycle = routes_per_cycle
        self.min_discount_pct = min_discount_pct
        self.routes = list(ML_CATEGORY_HUNTER_ROUTES)

    def get_next_routes_batch(self, batch_size: Optional[int] = None) -> List[Dict[str, str]]:
        size = batch_size or self.routes_per_cycle
        total = len(self.routes)
        if total == 0:
            return []

        raw_cursor = self.database.get_config("category_hunter_cursor", "0")
        try:
            cursor = int(raw_cursor or "0") % total
        except ValueError:
            cursor = 0

        selected = [self.routes[(cursor + i) % total] for i in range(size)]
        new_cursor = (cursor + size) % total
        self.database.set_config("category_hunter_cursor", str(new_cursor))
        return selected

    async def hunt_offers(
        self, batch_size: Optional[int] = None
    ) -> List[ScrapedOffer]:
        batch = self.get_next_routes_batch(batch_size=batch_size)
        logger.info(
            f"[Frente B - Mais Vendidos ML] Varrendo {len(batch)} rotas oficiais de categorias comissionadas."
        )

        approved: List[ScrapedOffer] = []
        seen_urls: set[str] = set()

        for route in batch:
            cat_key = route["category_key"]
            url = route["url"]
            html_text = await self.fetch_text(url)
            if not html_text:
                continue

            cards = parse_ml_cards(
                html_text,
                source_name="ml_bestsellers",
                require_previous_price=False,
                min_discount_pct=self.min_discount_pct,
                category_hint=cat_key,
            )
            for offer in cards:
                clean_key = offer.url.split("?")[0].split("#")[0]
                if clean_key in seen_urls:
                    continue
                comp = evaluate_ml_compliance(
                    title=offer.title,
                    url=offer.url,
                    condition=offer.condition,
                    seller_reputation=offer.seller_reputation,
                )
                if not comp.approved:
                    continue
                seen_urls.add(clean_key)
                approved.append(offer)

            await asyncio.sleep(0.35)

        logger.info(
            f"[Frente B - Mais Vendidos ML] {len(approved)} ofertas elegíveis coletadas."
        )
        return approved
