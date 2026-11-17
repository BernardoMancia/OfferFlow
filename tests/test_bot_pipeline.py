from __future__ import annotations

from pathlib import Path

import pytest

from affiliate.mercadolivre import build_fallback_affiliate_url, convert_to_affiliate_url
from affiliate.url_cleaner import (
    clean_store_url,
    detect_store,
    extract_offer_key,
)
from classifier.imported_filter import evaluate_imported_food
from classifier.topic_router import classify_offer_topic
from config import OFFICIAL_TOPICS, Settings
from database.db import DatabaseManager
from database.logger import get_logger
from scrapers.gatry import parse_gatry_html
from scrapers.ml_offers import parse_ml_cards
from scrapers.pelando import parse_pelando_html
from scrapers.promobit import parse_promobit_html
from telegram_bot.formatter import build_offer_keyboard, format_offer_message


def test_database_and_anti_repetition(tmp_path: Path) -> None:
    db_file = tmp_path / "test_bot.db"
    test_db = DatabaseManager(db_path=db_file)


    all_topics = test_db.get_all_topics()
    assert len(all_topics) == 6
    assert {t["topic_key"] for t in all_topics} == set(OFFICIAL_TOPICS.keys())
    assert len(test_db.get_pending_topics()) == 6


    test_db.set_topic_thread_id("doces_importados", 14)
    assert test_db.get_topic_thread_id("doces_importados") == 14
    assert len(test_db.get_pending_topics()) == 5


    offer_key = "ml:MLB39481029"
    assert test_db.can_post_offer(offer_key, 100.0) is True

    test_db.record_posted_offer(
        offer_key=offer_key,
        title="Barra Milka Oreo 300g",
        price=100.0,
        topic_key="doces_importados",
    )


    assert test_db.can_post_offer(offer_key, 100.0) is False
    assert test_db.can_post_offer(offer_key, 95.0) is False


    assert test_db.can_post_offer(offer_key, 90.0) is True
    assert test_db.can_post_offer(offer_key, 85.0) is True


def test_sqlite_central_logger(tmp_path: Path) -> None:
    log_db = tmp_path / "logs.db"
    test_logger = get_logger("test.module", db_path=log_db)
    test_logger.info("Mensagem de teste para SQLite Logger")

    import sqlite3

    conn = sqlite3.connect(str(log_db))
    row = conn.execute(
        "SELECT timestamp, level, source, message, raw_line FROM logs LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[1] == "INFO"
    assert row[2] == "test.module"
    assert "Mensagem de teste" in row[3]
    assert "[INFO]" in row[4]


@pytest.mark.asyncio
async def test_affiliate_url_cleaning_and_fallback() -> None:
    dirty_ml = (
        "https://produto.mercadolivre.com.br/MLB-39481029-chocolate-milka-oreo-100g-_JM"
        "?matt_tool=99999999&matt_word=pelando&tracking_id=abc#polycard"
    )
    cleaned = clean_store_url(dirty_ml)
    assert (
        cleaned
        == "https://produto.mercadolivre.com.br/MLB-39481029-chocolate-milka-oreo-100g-_JM"
    )
    assert extract_offer_key(dirty_ml) == "ml:MLB39481029"
    assert detect_store(dirty_ml) == "Mercado Livre"

    fallback = build_fallback_affiliate_url(
        cleaned, matt_tool="12345678", matt_word="meubot"
    )
    assert (
        fallback
        == "https://produto.mercadolivre.com.br/MLB-39481029-chocolate-milka-oreo-100g-_JM?matt_tool=12345678&matt_word=meubot"
    )

    custom_cfg = Settings(
        ml_matt_tool="88776655",
        ml_matt_word="promobot",
        ml_affiliate_cookie="",
        ml_affiliate_tag="",
    )
    converted = await convert_to_affiliate_url(dirty_ml, cfg=custom_cfg)
    assert "matt_tool=88776655" in converted
    assert "matt_word=promobot" in converted
    assert "pelando" not in converted


def test_imported_filter_strict_rules() -> None:

    for national in [
        "Caixa de Bombom Garoto 250g",
        "Pacote 1kg Bombom Sonho de Valsa Lacta",
        "Bombom Serenata de Amor 825g",
        "Chocolate Bis Xtra Ao Leite 45g",
        "Arroz Branco Tipo 1 5kg",
        "Feijão Carioca Camil 1kg",
        "Achocolatado em Pó Nescau 400g",
        "Leite Condensado Moça Nestlé 395g",
        "Pote Paçoca Rolha 1kg",
    ]:
        res = evaluate_imported_food(national)
        assert res.is_food_universe is True
        assert res.approved is False, f"Deveria bloquear nacional: {national}"
        assert classify_offer_topic(national, discount_pct=60) is None


    for sweet in [
        "Barra de Chocolate Importado Milka Mmmax Oreo 300g",
        "Trufas Chocolate Suíço Lindt Lindor Ao Leite 200g",
        "Chocolate Toblerone Ao Leite Com Mel e Amêndoas 100g",
        "Alfajor Argentino Havanna Chocolate Caixa 12 un",
        "Biscoito Importado Lotus Biscoff 250g Belga",
        "Bala Azedinha Sour Patch Kids Importada EUA",
        "Biscoito Palito Pocky Chocolate Glico",
    ]:
        res = evaluate_imported_food(sweet)
        assert res.approved is True, f"Deveria aprovar doce importado: {sweet}"
        assert res.topic_key == "doces_importados"
        assert classify_offer_topic(sweet, discount_pct=25) == "doces_importados"


    for food in [
        "Kit 5 Macarrão Lamen Coreano Samyang Buldak Carbonara",
        "Lámen Coreano Picante Shin Ramyun Nongshim 120g",
        "Salgadinho Takis Fuego Picante 92g",
        "Massa Italiana Spaghetti De Cecco 500g",
        "Molho de Tomate Italiano Passata Mutti 700g",
        "Pack 12 Refrigerante Importado Dr Pepper 355ml",
        "Café em Grãos Italiano Illy Clássico 250g",
        "Molho de Pimenta Sriracha Huy Fong 481g",
    ]:
        res = evaluate_imported_food(food)
        assert res.approved is True, f"Deveria aprovar comida importada: {food}"
        assert res.topic_key == "comidas_importadas"
        assert classify_offer_topic(food, discount_pct=25) == "comidas_importadas"


    blusa_res = evaluate_imported_food("Blusa Feminina Moletom Hering Algodão")
    assert blusa_res.is_food_universe is False
    assert (
        classify_offer_topic("Blusa Feminina Moletom Hering Algodão", discount_pct=25)
        == "moda_beleza"
    )
    assert (
        classify_offer_topic("Cafeteira Expresso Nespresso Essenza Mini", discount_pct=25)
        == "casa_eletro"
    )


def test_topic_router_all_categories() -> None:
    assert (
        classify_offer_topic("Placa de Vídeo RTX 4060 Ti 8GB GDDR6", discount_pct=20)
        == "tecnologia"
    )
    assert (
        classify_offer_topic("Fritadeira Elétrica Airfryer Mondial 4L", discount_pct=25)
        == "casa_eletro"
    )
    assert (
        classify_offer_topic("Tênis Nike Air Max Excee Masculino", discount_pct=30)
        == "moda_beleza"
    )
    assert (
        classify_offer_topic("Smart TV 55 Polegadas 4K OLED Samsung", discount_pct=50)
        == "bugs_imperdiveis"
    )


def test_formatter_visual_layout() -> None:
    offer = {
        "title": "Barra de Chocolate Importado Milka Mmmax Oreo 300g",
        "store": "Mercado Livre",
        "is_full": True,
        "original_price": 44.90,
        "price": 24.90,
        "discount_pct": 44,
        "coupon": "DOCE10",
        "affiliate_url": "https://mercadolivre.com/sec/2xYz9Ab",
        "topic_key": "doces_importados",
    }
    text = format_offer_message(offer)
    assert "🍫 <b>Barra de Chocolate Importado Milka Mmmax Oreo 300g</b>" in text
    assert "Mercado Livre ⚡ <b>Full</b>" in text
    assert "R$ 44,90" in text
    assert "R$ 24,90" in text
    assert "(44% OFF)" in text
    assert "<code>DOCE10</code>" in text

    kb = build_offer_keyboard(offer)
    btn = kb.inline_keyboard[0][0]
    assert "Pegar Promoção no Mercado Livre" in btn.text
    assert btn.url == "https://mercadolivre.com/sec/2xYz9Ab"


def test_scrapers_parsers() -> None:
    sample_ml_html = """
    <div class="poly-card">
      <img data-src="https://http2.mlstatic.com/D_NQ_NP_12345-I.webp" />
      <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-39481029-chocolate-milka-oreo-300g-_JM">
        Barra de Chocolate Importado Milka Mmmax Oreo 300g
      </a>
      <s class="andes-money-amount--previous">
        <span class="andes-money-amount__fraction">44</span>
        <span class="andes-money-amount__cents">90</span>
      </s>
      <div class="poly-price__current">
        <span class="andes-money-amount">
          <span class="andes-money-amount__fraction">24</span>
          <span class="andes-money-amount__cents">90</span>
        </span>
        <span class="andes-money-amount__discount">44% OFF</span>
      </div>
      <span class="poly-component__shipped-from" aria-label="Enviado pelo FULL">FULL</span>
    </div>
    """
    ml_items = parse_ml_cards(sample_ml_html, min_discount_pct=20)
    assert len(ml_items) == 1
    assert ml_items[0].price == 24.90
    assert ml_items[0].original_price == 44.90
    assert ml_items[0].discount_pct == 44
    assert ml_items[0].is_full is True
    assert ml_items[0].image_url == "https://http2.mlstatic.com/D_NQ_NP_12345-O.webp"

    sample_gatry_html = """
    <article class="promocao">
      <div class="imagem"><img src="https://gatry.com/img/prod.jpg" /></div>
      <div class="informacoes">
        <h3><a href="https://produto.mercadolivre.com.br/MLB-11223344-ssd-1tb-_JM">SSD Kingston NV2 1TB NVMe</a></h3>
        <p class="preco">R$ 349,90</p>
        <div class="comentario">Use o cupom: TECH10 no checkout</div>
      </div>
    </article>
    """
    gatry_items = parse_gatry_html(sample_gatry_html)
    assert len(gatry_items) == 1
    assert gatry_items[0].price == 349.90
    assert gatry_items[0].coupon == "TECH10"

    sample_pelando_html = """
    <html><body>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"deals":[{"title":"Chocolate Lindt Lindor 200g","price":39.9,"sourceUrl":"https://produto.mercadolivre.com.br/MLB-55667788-lindt-_JM","couponCode":"LINDT15"}]}}}
    </script>
    </body></html>
    """
    pelando_items = parse_pelando_html(sample_pelando_html)
    assert len(pelando_items) == 1
    assert pelando_items[0].price == 39.90
    assert pelando_items[0].coupon == "LINDT15"

    sample_promobit_html = """
    <html><body>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"offers":[{"offer_title":"Cafeteira Italiana Bialetti","offer_price":129.9,"offer_old_price":199.9,"offer_slug":"cafeteira-bialetti-123"}]}}}
    </script>
    </body></html>
    """
    promobit_items = parse_promobit_html(sample_promobit_html)
    assert len(promobit_items) == 1
    assert promobit_items[0].price == 129.90
    assert promobit_items[0].original_price == 199.90


@pytest.mark.asyncio
async def test_improvements_1_to_6(tmp_path: Path) -> None:
    from datetime import datetime
    from telegram_bot.formatter import extract_unit_hint
    from telegram_bot.publisher import is_quiet_hours


    db_file = tmp_path / "rr_bot.db"
    test_db = DatabaseManager(db_path=db_file)
    test_db.enqueue_offer(
        offer_key="amz:1",
        title="Item Casa Amazon",
        price=150.0,
        original_price=220.0,
        discount_pct=31,
        coupon=None,
        store="Amazon",
        is_full=False,
        image_url=None,
        affiliate_url="https://amazon.com.br/dp/1",
        original_url="https://amazon.com.br/dp/1",
        topic_key="casa_eletro",
    )
    test_db.enqueue_offer(
        offer_key="ml:2",
        title="Item Casa Mercado Livre",
        price=140.0,
        original_price=220.0,
        discount_pct=36,
        coupon=None,
        store="Mercado Livre",
        is_full=True,
        image_url=None,
        affiliate_url="https://mercadolivre.com.br/p/2",
        original_url="https://mercadolivre.com.br/p/2",
        topic_key="casa_eletro",
    )
    test_db.enqueue_offer(
        offer_key="ml:3",
        title="Chocolate Milka 300g",
        price=24.90,
        original_price=44.90,
        discount_pct=44,
        coupon=None,
        store="Mercado Livre",
        is_full=True,
        image_url=None,
        affiliate_url="https://mercadolivre.com.br/p/3",
        original_url="https://mercadolivre.com.br/p/3",
        topic_key="doces_importados",
    )

    first = test_db.get_next_pending_offer()
    assert first is not None
    assert first["topic_key"] == "doces_importados"
    test_db.mark_queue_item_sent(int(first["id"]))


    second = test_db.get_next_pending_offer()
    assert second is not None
    assert second["topic_key"] == "casa_eletro"
    assert second["store"] == "Mercado Livre"


    assert (
        classify_offer_topic(
            "Fralda Geriátrica Bigfral G 8 Unidades", discount_pct=55, price=19.90
        )
        is None
    )
    assert (
        classify_offer_topic(
            "Lençol Descartável Hospitalar Maca 50x50", discount_pct=60, price=29.90
        )
        is None
    )

    assert (
        classify_offer_topic(
            "Jogo de Potes Herméticos Cozinha", discount_pct=50, price=39.90
        )
        == "casa_eletro"
    )

    assert (
        classify_offer_topic(
            "Fritadeira Airfryer 4L", discount_pct=50, price=199.90
        )
        == "bugs_imperdiveis"
    )


    amz_cfg = Settings(
        ml_matt_tool="11223344",
        ml_matt_word="promobot",
        amazon_affiliate_tag="meucanal-20",
    )
    amz_url = await convert_to_affiliate_url(
        "https://www.amazon.com.br/dp/B09V3KXJPB?tag=pelando-20", cfg=amz_cfg
    )
    assert "tag=meucanal-20" in amz_url
    assert "pelando-20" not in amz_url


    hint_100g = extract_unit_hint("Barra Milka 300g", 24.90, topic_key="doces_importados")
    assert hint_100g is not None and "R$ 8,30" in hint_100g
    hint_liter = extract_unit_hint("Azeite Italiano 500ml", 39.90, topic_key="comidas_importadas")
    assert hint_liter is not None and "R$ 79,80" in hint_liter
    test_db.record_posted_offer("ml:hist1", "Milka 300g", 24.90, "doces_importados")
    assert test_db.is_historical_low("ml:hist1", 29.90) is False
    assert test_db.is_historical_low("ml:hist1", 19.90) is True


    assert is_quiet_hours(datetime(2026, 10, 19, 23, 45)) is True
    assert is_quiet_hours(datetime(2026, 10, 19, 3, 15)) is True
    assert is_quiet_hours(datetime(2026, 10, 19, 14, 0)) is False


    test_db.set_paused(True)
    assert test_db.is_paused() is True
    test_db.set_paused(False)
    assert test_db.is_paused() is False
    cleared = test_db.clear_pending_queue()
    assert cleared >= 1


def test_improvements_7_to_14(tmp_path: Path) -> None:
    from database.db import build_title_signature
    from telegram_bot.formatter import format_daily_top5_summary


    sig1 = build_title_signature("Gin Inglês Seagers 1l")
    sig2 = build_title_signature("Gin Inglês Seagers 1L - Nota Fiscal")
    assert sig1 == sig2

    db_file = tmp_path / "dedup_sig.db"
    test_db = DatabaseManager(db_path=db_file)
    qid1 = test_db.enqueue_offer(
        offer_key="ml:MLB111",
        title="Chocolate Importado Lindt Lindor 200g",
        price=39.90,
        affiliate_url="https://mercadolivre.com.br/p/111",
        topic_key="doces_importados",
    )
    assert qid1 is not None


    qid2 = test_db.enqueue_offer(
        offer_key="ml:MLB222",
        title="Chocolate Importado Lindt Lindor 200g Original",
        price=42.90,
        affiliate_url="https://mercadolivre.com.br/p/222",
        topic_key="doces_importados",
    )
    assert qid2 is None


    qid3 = test_db.enqueue_offer(
        offer_key="ml:MLB333",
        title="Chocolate Importado Lindt Lindor 200g",
        price=34.90,
        affiliate_url="https://mercadolivre.com.br/p/333",
        topic_key="doces_importados",
    )
    assert qid3 is None
    next_item = test_db.get_next_pending_offer()
    assert next_item is not None
    assert next_item["price"] == 34.90
    assert next_item["offer_key"] == "ml:MLB333"


    assert evaluate_imported_food("Xarope Dilute Para Drink Soda Italiana").approved is False
    assert evaluate_imported_food("Gin Inglês Seagers 1L").approved is False
    assert evaluate_imported_food("Torrada Inglesa Bauducco").approved is False


    offer_sample = {
        "title": "Monitor Gamer LG UltraGear 27 144Hz",
        "store": "Mercado Livre",
        "price": 999.00,
        "original_price": 1399.00,
        "discount_pct": 28,
        "installments": "em 10x R$ 99,90 sem juros",
        "affiliate_url": "https://mercadolivre.com/sec/abc",
        "topic_key": "tecnologia",
    }
    msg_html = format_offer_message(offer_sample)
    assert "💳 <b>Parcelamento:</b> <i>em 10x R$ 99,90 sem juros</i>" in msg_html
    assert "Publicado em" not in msg_html

    kb = build_offer_keyboard(offer_sample)
    assert len(kb.inline_keyboard) == 1


    test_db.mark_queue_item_sent(int(next_item["id"]))
    top5 = test_db.get_top_offers_last_24h(limit=5)
    assert len(top5) == 1
    summary_text = format_daily_top5_summary(top5)
    assert "TOP 5 MELHORES PROMOÇÕES DO DIA" in summary_text
    assert "Lindt Lindor 200g" in summary_text


def test_revision_fixes(tmp_path: Path) -> None:
    import base64
    import json
    from affiliate.url_cleaner import (
        extract_mlb_code,
        extract_pelando_jwt_url,
        is_aggregator_url,
    )
    from database.db import build_title_signature


    payload = {"url": "https://www.amazon.com.br/dp/B09V3KXJPB?tag=pelando-20&linkCode=ll2"}
    b64_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_jwt_url = f"https://dpl.pelando.com.br/r/eyJhbGciOiJIUzI1NiJ9.{b64_payload}.sig"
    decoded = extract_pelando_jwt_url(fake_jwt_url)
    assert decoded == payload["url"]
    assert clean_store_url(decoded) == "https://www.amazon.com.br/dp/B09V3KXJPB"


    mlbu_url = "https://www.mercadolivre.com.br/up/MLBU3182315457?pdp_filters=item_id:MLB5387489668#polycard_client=offers"
    assert extract_mlb_code(mlbu_url) == "MLBU3182315457"
    assert extract_offer_key(mlbu_url) == "ml:MLBU3182315457"

    dirty_shopee = "https://shopee.com.br/opaanlp/344381236/45506315078?__mobile__=1&gads_t_sig=VTJGc2RHVmtYMTlxTFVSVVRrdENkWVp3&mmp_pid=an_1122334455&uls_trackid=55f80a230037"
    assert clean_store_url(dirty_shopee) == "https://shopee.com.br/opaanlp/344381236/45506315078"


    assert is_aggregator_url("https://www.promobit.com.br/Redirect/to/2402292/") is True
    assert is_aggregator_url("https://www.pelando.com.br/d/12345") is True
    assert is_aggregator_url("https://www.mercadolivre.com.br/ofertas") is False


    for national_grocery in [
        "Cesta Básica Completa 22 Itens Alimentos",
        "Sardinha Com Óleo Coqueiro 125g",
        "Creme de Cebola Maggi 68g",
        "Pão de Forma Tradicional Visconti 400g",
        "Creatina Monohidratada 300g Pura",
        "Chocottone Bauducco 400g",
    ]:
        res = evaluate_imported_food(national_grocery)
        assert res.is_food_universe is True, f"Deveria ser alimento: {national_grocery}"
        assert res.approved is False, f"Deveria bloquear nacional: {national_grocery}"
        assert classify_offer_topic(national_grocery, discount_pct=50, price=25.0) is None

    for imported_gourmet in [
        ("Macarrão Italiano Spaghetti La Molisana 500g", "comidas_importadas"),
        ("Maionese Japonesa Kewpie 200g", "comidas_importadas"),
        ("Geleia Francesa St. Dalfour Morango 284g", "doces_importados"),
        ("Licor Importado Frangelico 700ml", "comidas_importadas"),
    ]:
        title, expected_topic = imported_gourmet
        assert classify_offer_topic(title, discount_pct=30, price=35.0) == expected_topic


    assert classify_offer_topic("Sabonete Líquido Dove Nutrição Profunda 2L", discount_pct=43, price=49.90) == "moda_beleza"
    assert classify_offer_topic("Densidade Acidificante Capilar 250g Lola From Rio", discount_pct=50, price=22.42) == "moda_beleza"
    assert classify_offer_topic("Aparelho de Barbear Prestobarba 3 Masculino", discount_pct=45, price=32.33) == "moda_beleza"
    assert classify_offer_topic("Caladryl Loção Pós Sol 100ml", discount_pct=54, price=26.99) == "moda_beleza"
    assert classify_offer_topic("Saco de Lixo 100 Litros Reforçado 50 Unidades", discount_pct=46, price=49.00) == "casa_eletro"
    assert classify_offer_topic("Caixa de Pilhas Alcalina Elgin AA 96 Unidades", discount_pct=42, price=149.92) == "casa_eletro"


    assert build_title_signature("Smartphone Samsung Galaxy S24 256GB") == build_title_signature("Celular Samsung Galaxy S24 256GB")


@pytest.mark.asyncio
async def test_all_new_improvements(tmp_path: Path) -> None:
    from affiliate.mercadolivre import (
        build_magalu_affiliate_url,
        build_shopee_affiliate_url,
    )
    from main import _build_admin_panel_view, _build_draft_preview_keyboard
    from telegram_bot.formatter import format_operational_report


    shopee_clean = "https://shopee.com.br/opaanlp/344381236/45506315078"
    shopee_aff = build_shopee_affiliate_url(shopee_clean, shopee_id="1122334455")
    assert "mmp_pid=an_1122334455" in shopee_aff
    assert "utm_medium=affiliates" in shopee_aff

    magalu_clean = "https://www.magazineluiza.com.br/fritadeira-air-fryer-mondial/p/123456700/ep/frel/"
    magalu_aff = build_magalu_affiliate_url(magalu_clean, magalu_slug="minhalojapromo")
    assert magalu_aff == "https://www.magazinevoce.com.br/minhalojapromo/fritadeira-air-fryer-mondial/p/123456700/ep/frel/"

    multi_cfg = Settings(
        shopee_affiliate_id="99887766",
        magalu_store_slug="vitrineoficial",
    )
    assert "an_99887766" in await convert_to_affiliate_url(shopee_clean, cfg=multi_cfg)
    assert "magazinevoce.com.br/vitrineoficial/" in await convert_to_affiliate_url(magalu_clean, cfg=multi_cfg)


    db_file = tmp_path / "improvements_all.db"
    test_db = DatabaseManager(db_path=db_file)
    test_db.record_posted_offer(
        offer_key="ml:MLB999888",
        title="Chocolate Suíço Lindt Lindor 200g",
        price=45.00,
        topic_key="doces_importados",
        original_url="https://produto.mercadolivre.com.br/MLB-999888",
        message_id=101,
        thread_id=14,
        has_photo=True,
    )
    hist_ctx = test_db.get_price_history_context("ml:MLB999888", 35.00, "Chocolate Suíço Lindt Lindor 200g")
    assert hist_ctx["is_historical_low"] is True
    assert hist_ctx["savings_vs_low"] == 10.00

    msg_html = format_offer_message(
        {
            "title": "Chocolate Suíço Lindt Lindor 200g",
            "store": "Mercado Livre",
            "price": 35.00,
            "original_price": 59.90,
            "discount_pct": 41,
            "affiliate_url": "https://mercadolivre.com/sec/xyz",
            "topic_key": "doces_importados",
            "is_historical_low": True,
            "savings_vs_low": 10.00,
        }
    )
    assert "R$ 10,00 abaixo do recorde anterior" in msg_html

    kb = build_offer_keyboard(
        {
            "title": "Chocolate Suíço Lindt Lindor 200g",
            "store": "Mercado Livre",
            "price": 35.00,
            "affiliate_url": "https://mercadolivre.com/sec/xyz",
        }
    )
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 2
    assert "Compartilhar" in kb.inline_keyboard[0][1].text


    recent_check = test_db.get_recent_posted_for_expiration_check(hours=2)
    assert len(recent_check) == 1
    assert recent_check[0]["message_id"] == 101
    test_db.mark_posted_offer_expired("ml:MLB999888")
    assert len(test_db.get_recent_posted_for_expiration_check(hours=2)) == 0


    qid = test_db.enqueue_offer(
        offer_key="ml:MLB777666",
        title="Fone Bluetooth JBL Tune 520BT",
        price=220.00,
        original_price=299.00,
        discount_pct=26,
        affiliate_url="https://mercadolivre.com/sec/jbl",
        topic_key="tecnologia",
        source="pelando",
    )
    assert qid is not None
    test_db.update_queue_item_price(qid, 199.00, 299.00)
    next_q = test_db.get_next_pending_offer()
    assert next_q is not None and next_q["price"] == 199.00 and next_q["discount_pct"] == 33
    assert test_db.remove_queue_item(qid) is True
    assert test_db.get_next_pending_offer() is None


    rep = test_db.get_24h_operational_report()
    rep_html = format_operational_report(rep)
    assert "RELATÓRIO OPERACIONAL (ÚLTIMAS 24H)" in rep_html
    panel_text, panel_kb = _build_admin_panel_view()
    assert "PAINEL DE CONTROLE DO ADMINISTRADOR" in panel_text
    assert len(panel_kb.inline_keyboard) == 4
    draft_kb = _build_draft_preview_keyboard("abc12345")
    assert len(draft_kb.inline_keyboard) == 2


    from scrapers.base import parse_brl_price

    assert parse_brl_price("R$ 4.099") == 4099.0
    assert parse_brl_price("R$ 1.689") == 1689.0
    assert parse_brl_price("R$ 1.249,90") == 1249.90
    assert parse_brl_price("R$ 24,90") == 24.90


    assert classify_offer_topic("(Steam) Jogo Resident Evil 4 Remake - PC", discount_pct=30, price=28.71) == "tecnologia"
    assert classify_offer_topic("MONDIAL Aparador de Pelos Super Groom 11", discount_pct=25, price=104.0) == "moda_beleza"
    assert classify_offer_topic("Whisky Escocês 12 Anos 1 Litro Chivas Regal", discount_pct=30, price=139.90) == "comidas_importadas"
    assert classify_offer_topic("Champan Francês Branco Brut Veuve Clicquot 750ml", discount_pct=25, price=376.93) == "comidas_importadas"
    assert classify_offer_topic("Kit Coala Home Chá Branco com Difusor 100ml", discount_pct=30, price=35.0) == "casa_eletro"


def test_next_level_5_improvements(tmp_path: Path) -> None:
    from telegram_bot.price_chart import generate_price_history_card
    from web.server import build_showcase_api_payload

    db_file = tmp_path / "next_level.db"
    test_db = DatabaseManager(db_path=db_file)


    aid1 = test_db.add_user_alert(1001, "rtx 4060", max_price=1950.0)
    aid2 = test_db.add_user_alert(1002, "milka", max_price=None)
    assert aid1 is not None and aid2 is not None
    assert len(test_db.list_user_alerts(1001)) == 1


    matches_gpu_cheap = test_db.match_user_alerts("Placa de Vídeo RTX 4060 8GB MSI", 1899.0)
    assert len(matches_gpu_cheap) == 1
    assert matches_gpu_cheap[0]["user_id"] == 1001


    matches_gpu_expensive = test_db.match_user_alerts("Placa de Vídeo RTX 4060 8GB MSI", 2299.0)
    assert len(matches_gpu_expensive) == 0


    assert test_db.remove_user_alert(1001, aid1) is True
    assert len(test_db.list_user_alerts(1001)) == 0


    test_db.enqueue_offer(
        offer_key="ml:MLB555444",
        title="Barra de Chocolate Importado Milka Oreo 300g",
        price=34.90,
        original_price=49.90,
        discount_pct=30,
        affiliate_url="https://mercadolivre.com/sec/milka",
        topic_key="doces_importados",
        rating=4.9,
        reviews_count=1280,
    )
    test_db.record_posted_offer(
        offer_key="ml:MLB555444",
        title="Barra de Chocolate Importado Milka Oreo 300g",
        price=24.90,
        original_price=49.90,
        topic_key="doces_importados",
        affiliate_url="https://mercadolivre.com/sec/milka",
        message_id=501,
        thread_id=14,
    )
    hist_points = test_db.get_offer_price_points("Milka Oreo")
    assert len(hist_points) >= 2
    assert min(float(p["price"]) for p in hist_points) == 24.90

    png_bytes = generate_price_history_card(hist_points[-1]["title"], hist_points)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 1500


    msg_with_rating = format_offer_message(
        {
            "title": "Barra de Chocolate Importado Milka Oreo 300g",
            "store": "Mercado Livre",
            "price": 24.90,
            "original_price": 49.90,
            "discount_pct": 50,
            "rating": 4.9,
            "reviews_count": 1280,
            "affiliate_url": "https://mercadolivre.com/sec/milka",
            "topic_key": "doces_importados",
        }
    )
    assert "⭐ <b>Avaliação:</b> 4.9/5.0 <i>(1.280 avaliações)</i>" in msg_with_rating


    low_rated_ml_html = """
    <div class="poly-card">
      <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-999-item-_JM">Produto Ruim</a>
      <div class="poly-price__current">
        <span class="andes-money-amount"><span class="andes-money-amount__fraction">50</span></span>
        <span class="andes-money-amount__discount">30% OFF</span>
      </div>
      <span class="poly-reviews__rating">3.2</span>
      <span class="poly-reviews__total">(45)</span>
    </div>
    """
    assert len(parse_ml_cards(low_rated_ml_html, min_discount_pct=20)) == 0

    high_rated_ml_html = """
    <div class="poly-card">
      <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-888-item-_JM">Produto Excelente</a>
      <div class="poly-price__current">
        <span class="andes-money-amount"><span class="andes-money-amount__fraction">50</span></span>
        <span class="andes-money-amount__discount">30% OFF</span>
      </div>
      <span class="poly-reviews__rating">4.8</span>
      <span class="poly-reviews__total">(320)</span>
    </div>
    """
    parsed_high = parse_ml_cards(high_rated_ml_html, min_discount_pct=20)
    assert len(parsed_high) == 1
    assert parsed_high[0].rating == 4.8
    assert parsed_high[0].reviews_count == 320


    showcase_payload = build_showcase_api_payload(database=test_db, search_query="Milka")
    assert showcase_payload["count"] == 1
    assert showcase_payload["offers"][0]["price"] == 34.90


    test_db.mark_posted_offer_expired("ml:MLB555444")
    to_delete = test_db.get_expired_offers_for_deletion(older_than_hours=0)
    assert len(to_delete) == 1
    assert to_delete[0]["message_id"] == 501
    test_db.mark_posted_offer_deleted("ml:MLB555444")
    assert len(test_db.get_expired_offers_for_deletion(older_than_hours=0)) == 0
