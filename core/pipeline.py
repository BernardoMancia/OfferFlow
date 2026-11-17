from __future__ import annotations

from typing import Sequence

import httpx

from affiliate.mercadolivre import convert_to_affiliate_url
from affiliate.url_cleaner import (
    detect_store,
    extract_offer_key,
    is_aggregator_url,
    unshorten_and_enrich_url,
)
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

            topic_key = classify_offer_topic(
                title=item.title,
                discount_pct=item.discount_pct,
                coupon=item.coupon,
                forced_food_check=forced_food_check,
                price=item.price,
            )
            if not topic_key:
                continue

            clean_url, discovered_coupon, discovered_store = (
                await unshorten_and_enrich_url(item.url, client=client)
            )
            if not clean_url or is_aggregator_url(clean_url):
                logger.debug(
                    f"Oferta ignorada por URL de agregador não resolvida: {item.url} -> {clean_url}"
                )
                continue

            effective_coupon = item.coupon or discovered_coupon
            if discovered_coupon and not item.coupon:
                topic_key = (
                    classify_offer_topic(
                        title=item.title,
                        discount_pct=item.discount_pct,
                        coupon=effective_coupon,
                        forced_food_check=forced_food_check,
                        price=item.price,
                    )
                    or topic_key
                )

            store_name = detect_store(clean_url)
            if store_name == "Loja Oficial":
                if discovered_store and discovered_store != "Loja Oficial":
                    store_name = discovered_store
                elif item.store:
                    store_name = item.store

            offer_key = extract_offer_key(clean_url, item.title)

            if not database.can_post_offer(offer_key, item.price, title=item.title):
                continue

            if item.source in ("pelando", "gatry") and (
                not item.original_price or not item.installments
            ):
                await enrich_offer_from_product_page(item, clean_url)
                if item.rating and 0 < float(item.rating) < settings.min_rating:
                    continue
                if item.discount_pct >= settings.bug_discount_pct:
                    topic_key = (
                        classify_offer_topic(
                            title=item.title,
                            discount_pct=item.discount_pct,
                            coupon=effective_coupon,
                            forced_food_check=forced_food_check,
                            price=item.price,
                        )
                        or topic_key
                    )

            affiliate_url = await convert_to_affiliate_url(
                clean_url, cfg=settings, client=client
            )
            if is_aggregator_url(affiliate_url):
                continue

            queue_id = database.enqueue_offer(
                offer_key=offer_key,
                title=item.title,
                price=item.price,
                original_price=item.original_price,
                discount_pct=item.discount_pct,
                coupon=effective_coupon,
                installments=item.installments,
                store=store_name,
                is_full=item.is_full,
                image_url=item.image_url,
                affiliate_url=affiliate_url,
                original_url=clean_url,
                topic_key=topic_key,
                source=item.source,
                rating=item.rating,
                reviews_count=item.reviews_count,
            )
            if queue_id is not None:
                enqueued_count += 1
                logger.info(
                    f"[Fila #{queue_id}] Enfileirada em [{topic_key}]: "
                    f"{item.title} | R$ {item.price:.2f} | Loja: {store_name}"
                )

    return enqueued_count
