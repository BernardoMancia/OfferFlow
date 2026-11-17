from __future__ import annotations

from affiliate.mercadolivre import convert_to_affiliate_url
from classifier.topic_router import classify_offer_topic
from config import settings
from database.db import db
from database.logger import get_logger

logger = get_logger("core.diagnostic")


async def run_local_diagnostic() -> int:
    logger.info("=== INICIANDO AUTODIAGNÓSTICO LOCAL ===")
    logger.info(f"Banco do Bot: {settings.db_path}")
    logger.info(f"Banco de Logs: {settings.log_db_path}")

    stats = db.get_stats()
    logger.info(f"Tópicos registrados no banco: {stats['total_topics']} categorias oficiais.")

    dirty_url = (
        "https://produto.mercadolivre.com.br/MLB-39481029-chocolate-milka-oreo-100g-_JM"
        "?matt_tool=99999999&matt_word=pelando&tracking_id=abc#polycard"
    )
    aff_url = await convert_to_affiliate_url(dirty_url)
    logger.info(f"Teste Afiliado ML -> Entrada suja: {dirty_url}")
    logger.info(f"Teste Afiliado ML -> Saída limpa/afiliada: {aff_url}")

    sample_cases = [
        ("Barra de Chocolate Importado Milka Mmmax Oreo 300g", 44, "DOCE10", 24.90),
        ("Caixa de Bombom Garoto 250g Serenata de Amor", 50, None, 12.90),
        ("Kit 5 Lamen Coreano Samyang Buldak Carbonara Importado", 25, None, 49.90),
        ("Arroz Branco Tipo 1 Tio João 5kg", 30, None, 26.90),
        ("Placa de Vídeo RTX 4060 8GB GDDR6", 22, None, 1899.00),
        ("Fritadeira Elétrica Airfryer Philips Walita 4L", 35, None, 349.90),
        ("Perfume Importado La Vie Est Belle Lancôme 100ml EDP", 28, None, 459.00),
        ("Notebook Gamer Acer Nitro V15 RTX 3050", 48, "BUG50", 3699.00),
        ("Fralda Geriátrica Descartável Bigfral G 8 Unidades", 52, None, 19.90),
        ("Xarope Dilute Para Drink Soda Italiana", 20, None, 29.90),
    ]
    for title, disc, cupom, price in sample_cases:
        routed = classify_offer_topic(title, discount_pct=disc, coupon=cupom, price=price)
        logger.info(f"Classificador: '{title}' (R$ {price:.2f}, {disc}% OFF) -> Tópico: {routed}")

    logger.info("=== AUTODIAGNÓSTICO CONCLUÍDO COM SUCESSO ===")
    return 0
