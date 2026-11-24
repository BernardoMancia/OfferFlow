from __future__ import annotations

from typing import Sequence

import httpx

from affiliate.mercadolivre import convert_to_affiliate_url, is_monetized_ml_url
from affiliate.url_cleaner import (
    extract_offer_key,
    is_aggregator_url,
    is_mercadolivre_url,
    unshorten_and_enrich_url,
)
from classifier.ml_compliance import evaluate_ml_compliance
from classifier.topic_router import classify_offer_topic
from config import settings
from database.db import DatabaseManager, db
from database.logger import get_logger
from scrapers.base import ScrapedOffer
from scrapers.ml_offers import enrich_offer_from_product_page

logger = get_logger("core.pipeline")


async def ingest_scraped_offers(
    offers: Sequence[ScrapedOffer],
    database: DatabaseManager = db,
    forced_food_check: bool = False,
) -> int:
    if not offers:
        return 0

    enqueued_count = 0
    async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
        for item in offers:
            if item.rating and 0 < float(item.rating) < settings.min_rating:
                continue

            clean_url, discovered_coupon, _ = await unshorten_and_enrich_url(
                item.url, client=client
            )
            if not clean_url or is_aggregator_url(clean_url):
                continue

            if settings.ml_only_mode and not is_mercadolivre_url(clean_url):
                continue

            effective_coupon = item.coupon or discovered_coupon

            pre_comp = evaluate_ml_compliance(
                title=item.title,
                url=clean_url,
                condition=item.condition,
                seller_reputation=item.seller_reputation,
            )
            if not pre_comp.approved:
                continue

            offer_key = extract_offer_key(clean_url, item.title)
            if not database.can_post_offer(offer_key, item.price, title=item.title):
                continue

            if (
                not item.original_price
                or not item.installments
                or not item.seller_reputation
            ):
                await enrich_offer_from_product_page(item, clean_url)
                if item.rating and 0 < float(item.rating) < settings.min_rating:
                    continue

            final_comp = evaluate_ml_compliance(
                title=item.title,
                url=clean_url,
                condition=item.condition,
                seller_reputation=item.seller_reputation,
            )
            if not final_comp.approved:
                logger.debug(
                    f"Oferta barrada após enriquecimento ML: '{item.title}' ({final_comp.reason})"
                )
                continue

            topic_key = classify_offer_topic(
                title=item.title,
                discount_pct=item.discount_pct,
                coupon=effective_coupon,
                price=item.price,
                url=clean_url,
                condition=final_comp.normalized_condition,
                seller_reputation=final_comp.normalized_reputation,
                category_hint=item.category_hint,
            )
            if not topic_key:
                continue

            affiliate_url = await convert_to_affiliate_url(
                clean_url, cfg=settings, client=client
            )
            if not affiliate_url or is_aggregator_url(affiliate_url):
                continue
            if settings.require_affiliate_link and not is_monetized_ml_url(affiliate_url):
                continue

            queue_id = database.enqueue_offer(
                offer_key=offer_key,
                title=item.title,
                price=item.price,
                original_price=item.original_price,
                discount_pct=item.discount_pct,
                coupon=effective_coupon,
                installments=item.installments,
                store="Mercado Livre",
                is_full=item.is_full,
                image_url=item.image_url,
                affiliate_url=affiliate_url,
                original_url=clean_url,
                topic_key=topic_key,
                source=item.source,
                rating=item.rating,
                reviews_count=item.reviews_count,
                condition=final_comp.normalized_condition,
                seller_reputation=final_comp.normalized_reputation,
            )
            if queue_id is not None:
                enqueued_count += 1
                logger.info(
                    f"[Fila #{queue_id}] Enfileirada em [{topic_key}]: "
                    f"{item.title} | R$ {item.price:.2f} | Cond: {final_comp.normalized_condition}"
                )

    return enqueued_count
