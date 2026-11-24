from __future__ import annotations

import asyncio
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import settings
from core.pipeline import ingest_scraped_offers
from core.telemetry import send_heartbeat, write_app_manifest
from database.db import db
from database.logger import get_logger
from scrapers.base import ScrapedOffer
from scrapers.gatry import GatryScraper
from scrapers.ml_category_hunter import MercadoLivreCategoryHunter
from scrapers.ml_offers import MercadoLivreOffersScraper
from scrapers.pelando import PelandoScraper
from scrapers.promobit import PromobitScraper
from telegram_bot.channel_manager import configure_bot_profile
from telegram_bot.publisher import (
    check_and_mark_expired_offers,
    process_next_queued_offer,
    publish_daily_admin_report,
    publish_daily_top5_summary,
)
from telegram_bot.setup_topics import ensure_forum_topics, lock_group_for_non_admins
from web.server import start_showcase_web_server

logger = get_logger("core.scheduler")


async def job_scrape_aggregators() -> int:
    logger.info("Iniciando ciclo Frente C (Agregadores filtrados 100% Mercado Livre)...")
    pelando = PelandoScraper()
    promobit = PromobitScraper()
    gatry = GatryScraper()

    results = await asyncio.gather(
        pelando.fetch_offers(),
        promobit.fetch_offers(),
        gatry.fetch_offers(),
        return_exceptions=True,
    )

    combined: List[ScrapedOffer] = []
    for res in results:
        if isinstance(res, list):
            combined.extend(res)
        elif isinstance(res, Exception):
            logger.error(f"Erro em coletor de agregador: {res}")

    added = await ingest_scraped_offers(combined)
    logger.info(
        f"Ciclo Frente C concluído: {len(combined)} brutas -> {added} ML elegíveis na fila."
    )
    return added


async def job_scrape_ml_offers() -> int:
    logger.info("Iniciando ciclo Frente A (Ofertas Oficiais e Relâmpago ML)...")
    scraper = MercadoLivreOffersScraper()
    offers = await scraper.fetch_offers()
    added = await ingest_scraped_offers(offers)
    logger.info(
        f"Ciclo Frente A concluído: {len(offers)} brutas -> {added} aprovadas na fila."
    )
    return added


async def job_scrape_ml_categories() -> int:
    logger.info("Iniciando ciclo Frente B (Mais Vendidos por Categoria Oficial ML)...")
    hunter = MercadoLivreCategoryHunter(database=db)
    offers = await hunter.hunt_offers()
    added = await ingest_scraped_offers(offers)
    logger.info(
        f"Ciclo Frente B concluído: {len(offers)} coletadas -> {added} aprovadas na fila."
    )
    return added


async def post_init(application: Application) -> None:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        job_scrape_ml_offers,
        "interval",
        minutes=settings.ml_offers_interval_min,
        id="frente_a_ml_offers",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        job_scrape_ml_categories,
        "interval",
        minutes=settings.ml_hunter_interval_min,
        id="frente_b_ml_categories",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        job_scrape_aggregators,
        "interval",
        minutes=settings.aggregator_interval_min,
        id="frente_c_agregadores_ml",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        process_next_queued_offer,
        "interval",
        seconds=settings.publish_interval_sec,
        args=[application.bot, db],
        id="publisher_queue",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        publish_daily_top5_summary,
        "cron",
        hour=20,
        minute=0,
        args=[application.bot, db],
        id="daily_top5_summary",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        check_and_mark_expired_offers,
        "interval",
        minutes=20,
        args=[application.bot, db],
        id="detector_oferta_encerrada",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        publish_daily_admin_report,
        "cron",
        hour=21,
        minute=0,
        args=[application.bot, db],
        id="daily_admin_report",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        send_heartbeat,
        "interval",
        seconds=60,
        id="telemetry_heartbeat",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    write_app_manifest()
    logger.info(
        "Agendador APScheduler iniciado (100% Mercado Livre): "
        f"Ofertas ML={settings.ml_offers_interval_min}m, "
        f"Mais Vendidos={settings.ml_hunter_interval_min}m, "
        f"Agregadores ML-Only={settings.aggregator_interval_min}m, "
        f"Publicador={settings.publish_interval_sec}s."
    )

    await configure_bot_profile(application.bot)

    web_runner = await start_showcase_web_server(port=settings.web_port, database=db)
    if web_runner:
        application.bot_data["web_runner"] = web_runner

    async def _initial_warmup() -> None:
        try:
            chat_id = db.get_chat_id()
            if chat_id and not db.get_linked_category_keys():
                try:
                    await application.bot.get_chat(chat_id)
                    await lock_group_for_non_admins(application.bot, chat_id)
                    if db.get_pending_topics():
                        await ensure_forum_topics(application.bot, chat_id, database=db)
                except Exception:
                    logger.info(
                        "Aguardando vinculação dos novos canais da Comunidade OfferFlow (use /vincular hub e /vincular <categoria>)."
                    )
            await job_scrape_ml_offers()
            await process_next_queued_offer(application.bot, db)
        except Exception as exc:
            logger.error(f"Erro no ciclo inicial de aquecimento: {exc}")

    asyncio.create_task(_initial_warmup())
