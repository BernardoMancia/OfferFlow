from __future__ import annotations

from affiliate.mercadolivre import convert_to_affiliate_url, has_active_ml_affiliate
from classifier.topic_router import classify_offer_topic
from config import settings
from database.db import db
from database.logger import get_logger

logger = get_logger("core.diagnostic")


async def run_local_diagnostic() -> int:
    logger.info("=== INICIANDO AUTODIAGNÓSTICO LOCAL (OFFERFLOW v2.0 ML-ONLY) ===")
    logger.info(f"Banco do Bot: {settings.db_path}")
    logger.info(f"Banco de Logs: {settings.log_db_path}")

    stats = db.get_stats()
    logger.info(
        f"Canais vinculados: {stats['linked_channels']}/{stats['total_channels']} | Hub: {stats['hub_linked']}"
    )
    logger.info(
        f"Afiliado ML ativo: {has_active_ml_affiliate()} | Trava de monetização: {settings.require_affiliate_link}"
    )

    dirty_url = (
        "https://produto.mercadolivre.com.br/MLB-39481029-monitor-gamer-lg-27-_JM"
        "?matt_tool=99999999&matt_word=pelando&tracking_id=abc#polycard"
    )
    aff_url = await convert_to_affiliate_url(dirty_url)
    logger.info(f"Teste Afiliado ML -> Saída: {aff_url or '(bloqueado até configurar /configurar_afiliado)'}")

    sample_cases = [
        ("Monitor Gamer LG UltraGear 27 180Hz IPS", 35, None, 899.00, "new", "green"),
        ("Notebook Gamer Acer Nitro V15 RTX 3050", 48, "BUG50", 3699.00, "new", "green"),
        ("Parafusadeira Furadeira Bosch GSB 18V", 30, None, 489.00, "new", "yellow"),
        ("Ração Golden Special Cães Adultos 15kg", 25, None, 149.90, "new", "green"),
        ("Barra de Chocolate Importado Milka Oreo 300g", 44, None, 24.90, "new", "green"),
        ("iPhone 13 128GB Usado com marcas de uso", 40, None, 2199.00, "used", "green"),
        ("Termômetro Clínico Hospitalar + Seringa", 50, None, 39.90, "new", "green"),
        ("PlayStation 5 Slim 1TB Novo", 22, None, 3499.00, "new", "red"),
    ]
    for title, disc, cupom, price, cond, rep in sample_cases:
        routed = classify_offer_topic(
            title,
            discount_pct=disc,
            coupon=cupom,
            price=price,
            condition=cond,
            seller_reputation=rep,
        )
        logger.info(
            f"Compliance & Roteador: '{title}' (cond={cond}, rep={rep}) -> Canal: {routed}"
        )

    logger.info("=== AUTODIAGNÓSTICO CONCLUÍDO COM SUCESSO ===")
    return 0
