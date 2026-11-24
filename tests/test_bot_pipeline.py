from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from affiliate.mercadolivre import (
    build_fallback_affiliate_url,
    convert_to_affiliate_url,
    extract_affiliate_params_from_url,
    is_monetized_ml_url,
)
from affiliate.url_cleaner import (
    clean_store_url,
    detect_store,
    extract_mlb_code,
    extract_offer_key,
    extract_pelando_jwt_url,
    is_aggregator_url,
)
from classifier.catalogs import CHANNEL_CATALOG, OFFICIAL_TOPICS
from classifier.ml_compliance import evaluate_ml_compliance, is_valid_ml_product_or_list_url
from classifier.topic_router import classify_offer_topic
from config import Settings
from database.db import DatabaseManager, build_title_signature
from database.logger import get_logger
from scrapers.base import parse_brl_price
from scrapers.gatry import parse_gatry_html
from scrapers.ml_offers import parse_ml_cards
from scrapers.pelando import parse_pelando_html
from scrapers.promobit import parse_promobit_html
from telegram_bot.formatter import (
    build_hub_directory_keyboard,
    build_offer_keyboard,
    extract_unit_hint,
    format_daily_top5_summary,
    format_hub_directory_message,
    format_offer_message,
    format_operational_report,
)
from telegram_bot.price_chart import generate_price_history_card
from telegram_bot.publisher import is_quiet_hours
from web.server import build_showcase_api_payload


def test_database_multichannel_and_anti_repetition(tmp_path: Path) -> None:
    db_file = tmp_path / "test_offerflow.db"
    test_db = DatabaseManager(db_path=db_file)

    all_topics = test_db.get_all_topics()
    assert len(all_topics) == 8
    assert {t["topic_key"] for t in all_topics} == set(OFFICIAL_TOPICS.keys())

    all_channels = test_db.get_all_channels(include_hub=True)
    assert len(all_channels) == 9
    assert {c["category_key"] for c in all_channels} == set(CHANNEL_CATALOG.keys())

    assert test_db.bind_channel("hub", -10011, username="comunidade_teste", invite_url="https://t.me/comunidade_teste") is True
    assert test_db.bind_channel("tech_celulares", -10022, username="tech_teste", invite_url="https://t.me/tech_teste") is True
    assert test_db.get_channel_chat_id("tech_celulares") == -10022
    assert test_db.get_linked_category_keys() == ["tech_celulares"]

    test_db.set_folder_url("https://t.me/addlist/exemplo123")
    assert test_db.get_folder_url() == "https://t.me/addlist/exemplo123"

    test_db.add_admin_user_id(998877)
    assert 998877 in test_db.get_admin_user_ids()

    offer_key = "ml:MLB39481029"
    assert test_db.can_post_offer(offer_key, 1000.0) is True
    test_db.record_posted_offer(
        offer_key=offer_key,
        title="Monitor Gamer LG UltraGear 27",
        price=1000.0,
        topic_key="tech_celulares",
        target_chat_id=-10022,
        message_id=77,
    )
    assert test_db.can_post_offer(offer_key, 1000.0) is False
    assert test_db.can_post_offer(offer_key, 950.0) is False
    assert test_db.can_post_offer(offer_key, 899.0) is True


def test_sqlite_central_logger(tmp_path: Path) -> None:
    log_db = tmp_path / "logs.db"
    test_logger = get_logger("test.module", db_path=log_db)
    test_logger.info("Mensagem de teste para SQLite Logger")

    conn = sqlite3.connect(str(log_db))
    row = conn.execute(
        "SELECT timestamp, level, source, message, raw_line FROM logs LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[1] == "INFO"
    assert row[2] == "test.module"
    assert "Mensagem de teste" in row[3]


@pytest.mark.asyncio
async def test_ml_only_affiliate_guard_and_extractor() -> None:
    dirty_ml = (
        "https://produto.mercadolivre.com.br/MLB-39481029-monitor-lg-27-_JM"
        "?matt_tool=99999999&matt_word=pelando&tracking_id=abc#polycard"
    )
    cleaned = clean_store_url(dirty_ml)
    assert cleaned == "https://produto.mercadolivre.com.br/MLB-39481029-monitor-lg-27-_JM"
    assert extract_offer_key(dirty_ml) == "ml:MLB39481029"
    assert detect_store(dirty_ml) == "Mercado Livre"

    extracted = await extract_affiliate_params_from_url(dirty_ml)
    assert extracted["ml_matt_tool"] == "99999999"
    assert extracted["ml_matt_word"] == "pelando"

    fallback = build_fallback_affiliate_url(cleaned, matt_tool="12345678", matt_word="offerflow")
    assert fallback == "https://produto.mercadolivre.com.br/MLB-39481029-monitor-lg-27-_JM?matt_tool=12345678&matt_word=offerflow"
    assert is_monetized_ml_url(fallback) is True
    assert is_monetized_ml_url(cleaned) is False

    strict_valid_cfg = Settings(
        ml_only_mode=True,
        require_affiliate_link=True,
        ml_matt_tool="11223344",
        ml_matt_word="offerflow",
        ml_affiliate_cookie="",
        ml_affiliate_tag="",
    )
    converted = await convert_to_affiliate_url(dirty_ml, cfg=strict_valid_cfg)
    assert "matt_tool=11223344" in converted
    assert "matt_word=offerflow" in converted
    assert "pelando" not in converted

    assert await convert_to_affiliate_url("https://www.amazon.com.br/dp/B09V3KXJPB", cfg=strict_valid_cfg) == ""
    assert await convert_to_affiliate_url("https://shopee.com.br/opaanlp/123/456", cfg=strict_valid_cfg) == ""

    strict_missing_cfg = Settings(
        ml_only_mode=True,
        require_affiliate_link=True,
        ml_matt_tool="SEU_MATT_TOOL",
        ml_matt_word="SEU_MATT_WORD",
        ml_affiliate_cookie="",
        ml_affiliate_tag="",
    )
    assert await convert_to_affiliate_url(dirty_ml, cfg=strict_missing_cfg) == ""


def test_ml_affiliate_official_compliance_and_8_channels() -> None:
    valid_url = "https://produto.mercadolivre.com.br/MLB-55667788-produto-teste-_JM"

    for generic_url in [
        "https://www.mercadolivre.com.br/",
        "https://www.mercadolivre.com.br/categorias",
        "https://www.mercadolivre.com.br/cart",
        "https://minhaloja.mercadoshops.com.br/MLB-123",
        "https://www.amazon.com.br/dp/B09V3KXJPB",
    ]:
        assert is_valid_ml_product_or_list_url(generic_url) is False
        assert evaluate_ml_compliance("Notebook Acer", url=generic_url).approved is False

    for blocked_title in [
        "Barra de Chocolate Importado Milka Oreo 300g",
        "Whisky Escocês 12 Anos Chivas Regal 1L",
        "Café em Grãos Italiano Illy 250g",
        "Azeite de Oliva Extra Virgem 500ml",
        "Fórmula Infantil Aptamil Premium 800g",
        "Whey Protein Concentrado 900g",
        "Dipirona Monoidratada 500mg 20 Comprimidos",
        "Termômetro Clínico Digital Hospitalar",
        "Fralda Geriátrica Bigfral G 8 Unidades",
        "iPhone 13 128GB Usado Seminovo",
        "Filhote de Golden Retriever com Pedigree",
        "Ingresso Show Rock Festival Pista",
        "Aluguel de Apartamento 2 Quartos",
        "Trator Agrícola 4x4 2024",
    ]:
        res = evaluate_ml_compliance(blocked_title, url=valid_url)
        assert res.approved is False, f"Deveria bloquear: {blocked_title}"
        assert classify_offer_topic(blocked_title, discount_pct=50, price=200.0, url=valid_url) is None

    assert evaluate_ml_compliance("Notebook Dell", url=valid_url, condition="used").approved is False
    assert evaluate_ml_compliance("Notebook Dell", url=valid_url, condition="refurbished", seller_reputation="green").approved is True
    assert evaluate_ml_compliance("Box Livros Harry Potter", url=valid_url, condition="refurbished", seller_reputation="green").approved is False
    assert evaluate_ml_compliance("Box Livros Harry Potter", url=valid_url, condition="new", seller_reputation="green").approved is True
    assert evaluate_ml_compliance("Monitor LG 27", url=valid_url, condition="new", seller_reputation="red").approved is False
    assert evaluate_ml_compliance("Monitor LG 27", url=valid_url, condition="new", seller_reputation="orange").approved is False
    assert evaluate_ml_compliance("Monitor LG 27", url=valid_url, condition="new", seller_reputation="yellow").approved is True
    assert evaluate_ml_compliance("Monitor LG 27", url=valid_url, condition="new", seller_reputation="green").approved is True

    assert classify_offer_topic("Smart TV 55 4K OLED Samsung", discount_pct=50, price=3200.0, url=valid_url) == "ofertas_bugs"
    assert classify_offer_topic("Placa de Vídeo RTX 4060 8GB GDDR6", discount_pct=25, price=1899.0, url=valid_url) == "tech_celulares"
    assert classify_offer_topic("PlayStation 5 Slim 1TB + Jogo", discount_pct=22, price=3499.0, url=valid_url) == "games_geek"
    assert classify_offer_topic("Box Livros O Senhor dos Anéis Capa Dura", discount_pct=25, price=129.90, url=valid_url) == "games_geek"
    assert classify_offer_topic("Cafeteira Expresso Nespresso Essenza Mini", discount_pct=25, price=399.0, url=valid_url) == "casa_eletro"
    assert classify_offer_topic("Fritadeira Elétrica Airfryer Philips Walita 4L", discount_pct=30, price=349.0, url=valid_url) == "casa_eletro"
    assert classify_offer_topic("Furadeira Parafusadeira Bosch GSB 18V", discount_pct=28, price=499.0, url=valid_url) == "ferramentas_construcao"
    assert classify_offer_topic("Tênis Nike Air Max Excee Masculino", discount_pct=30, price=329.0, url=valid_url) == "moda_relogios"
    assert classify_offer_topic("Perfume La Vie Est Belle Lancôme 100ml", discount_pct=25, price=459.0, url=valid_url) == "beleza_esportes"
    assert classify_offer_topic("Bicicleta Ergométrica Spinning Profissional", discount_pct=25, price=1199.0, url=valid_url) == "beleza_esportes"
    assert classify_offer_topic("Ração Golden Special Cães Adultos 15kg", discount_pct=22, price=149.90, url=valid_url) == "pet_bebes_papelaria"
    assert classify_offer_topic("Carrinho de Bebê Burigotto Passeio", discount_pct=25, price=799.0, url=valid_url) == "pet_bebes_papelaria"
    assert classify_offer_topic("Violão Elétrico Giannini Aço Folk", discount_pct=25, price=599.0, url=valid_url) == "pet_bebes_papelaria"


def test_editorial_premium_formatter_and_hub_directory(tmp_path: Path) -> None:
    offer = {
        "title": "Monitor Gamer LG UltraGear 27 IPS 180Hz 1ms Full HD",
        "store": "Mercado Livre",
        "is_full": True,
        "original_price": 1399.00,
        "price": 899.00,
        "discount_pct": 36,
        "installments": "em 10x de R$ 89,90 sem juros",
        "coupon": "MELI10",
        "rating": 4.9,
        "reviews_count": 1420,
        "condition": "new",
        "seller_reputation": "green",
        "is_historical_low": True,
        "savings_vs_low": 80.0,
        "affiliate_url": "https://mercadolivre.com/sec/2xYz9Ab",
        "topic_key": "tech_celulares",
    }
    text = format_offer_message(offer)
    assert "TECH, INFORMÁTICA &amp; CELULARES" in text
    assert "━━━━━━━━━━━━━━━━━━━━" in text
    assert "R$ 1.399,00" in text
    assert "R$ 899,00" in text
    assert "(-36% OFF)" in text
    assert "Vendedor Verde" in text
    assert "Envio FULL" in text
    assert "Novo" in text
    assert "4.9/5.0" in text
    assert "1.420 avaliações" in text
    assert "R$ 80,00 abaixo do recorde" in text
    assert "<code>MELI10</code>" in text
    assert "Curadoria OfferFlow" in text

    kb = build_offer_keyboard(offer, hub_url="https://t.me/offerflow_hub")
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].text == "🛒 Garantir no Mercado Livre"
    assert kb.inline_keyboard[0][0].url == "https://mercadolivre.com/sec/2xYz9Ab"
    assert len(kb.inline_keyboard[1]) == 2
    assert "Comunidade OfferFlow" in kb.inline_keyboard[1][1].text

    channels_sample = [
        {"category_key": "tech_celulares", "chat_id": -1001, "invite_url": "https://t.me/tech_of"},
        {"category_key": "casa_eletro", "chat_id": -1002, "invite_url": "https://t.me/casa_of"},
    ]
    hub_msg = format_hub_directory_message(channels_sample, folder_url="https://t.me/addlist/abc")
    assert "BEM-VINDO À COMUNIDADE OFFERFLOW" in hub_msg
    assert "Tech, Informática &amp; Celulares" in hub_msg
    hub_kb = build_hub_directory_keyboard(channels_sample, folder_url="https://t.me/addlist/abc")
    assert "Adicionar Pasta Completa" in hub_kb.inline_keyboard[0][0].text
    assert len(hub_kb.inline_keyboard) == 2


def test_scrapers_parsers_condition_and_rating() -> None:
    sample_ml_html = """
    <div class="poly-card">
      <img data-src="https://http2.mlstatic.com/D_NQ_NP_12345-I.webp" />
      <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-39481029-monitor-lg-27-_JM">
        Monitor Gamer LG UltraGear 27 IPS 180Hz
      </a>
      <s class="andes-money-amount--previous">
        <span class="andes-money-amount__fraction">1.399</span>
        <span class="andes-money-amount__cents">00</span>
      </s>
      <div class="poly-price__current">
        <span class="andes-money-amount">
          <span class="andes-money-amount__fraction">899</span>
          <span class="andes-money-amount__cents">00</span>
        </span>
        <span class="andes-money-amount__discount">36% OFF</span>
      </div>
      <span class="poly-reviews__rating">4.9</span>
      <span class="poly-reviews__total">(1,4 mil)</span>
      <span class="poly-component__shipped-from" aria-label="Enviado pelo FULL">FULL</span>
    </div>
    <div class="poly-card">
      <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-999-usado-_JM">iPhone 13 Usado</a>
      <span class="poly-component__condition">Usado</span>
      <div class="poly-price__current">
        <span class="andes-money-amount"><span class="andes-money-amount__fraction">1800</span></span>
        <span class="andes-money-amount__discount">40% OFF</span>
      </div>
    </div>
    <div class="poly-card">
      <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-888-ruim-_JM">Fone Sem Marca</a>
      <div class="poly-price__current">
        <span class="andes-money-amount"><span class="andes-money-amount__fraction">50</span></span>
        <span class="andes-money-amount__discount">30% OFF</span>
      </div>
      <span class="poly-reviews__rating">3.1</span>
    </div>
    """
    ml_items = parse_ml_cards(sample_ml_html, min_discount_pct=20)
    assert len(ml_items) == 1
    assert ml_items[0].price == 899.00
    assert ml_items[0].original_price == 1399.00
    assert ml_items[0].discount_pct == 36
    assert ml_items[0].is_full is True
    assert ml_items[0].rating == 4.9
    assert ml_items[0].reviews_count == 1400
    assert ml_items[0].condition == "new"
    assert ml_items[0].image_url == "https://http2.mlstatic.com/D_NQ_NP_12345-O.webp"

    assert parse_brl_price("R$ 4.099") == 4099.0
    assert parse_brl_price("R$ 1.249,90") == 1249.90
    assert parse_brl_price("R$ 24,90") == 24.90

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
    assert gatry_items[0].coupon == "TECH10"

    sample_pelando_html = """
    <html><body>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"deals":[{"title":"Monitor LG 27","price":899.9,"sourceUrl":"https://produto.mercadolivre.com.br/MLB-55667788-lg-_JM","couponCode":"TECH15"}]}}}
    </script>
    </body></html>
    """
    pelando_items = parse_pelando_html(sample_pelando_html)
    assert len(pelando_items) == 1
    assert pelando_items[0].coupon == "TECH15"

    sample_promobit_html = """
    <html><body>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"offers":[{"offer_title":"Cafeteira Italiana Bialetti","offer_price":129.9,"offer_old_price":199.9,"offer_slug":"cafeteira-bialetti-123"}]}}}
    </script>
    </body></html>
    """
    promobit_items = parse_promobit_html(sample_promobit_html)
    assert len(promobit_items) == 1


def test_alerts_charts_showcase_expiry_and_panel(tmp_path: Path) -> None:
    from main import _build_admin_panel_view, _build_draft_preview_keyboard

    db_file = tmp_path / "full_features.db"
    test_db = DatabaseManager(db_path=db_file)

    aid1 = test_db.add_user_alert(1001, "rtx 4060", max_price=1950.0)
    assert aid1 is not None
    assert len(test_db.match_user_alerts("Placa de Vídeo RTX 4060 8GB MSI", 1899.0)) == 1
    assert len(test_db.match_user_alerts("Placa de Vídeo RTX 4060 8GB MSI", 2299.0)) == 0
    assert test_db.remove_user_alert(1001, aid1) is True

    test_db.enqueue_offer(
        offer_key="ml:MLB555444",
        title="Monitor Gamer LG UltraGear 27 IPS",
        price=999.00,
        original_price=1399.00,
        discount_pct=29,
        affiliate_url="https://mercadolivre.com/sec/lg27",
        topic_key="tech_celulares",
        rating=4.9,
        reviews_count=1280,
        condition="new",
        seller_reputation="green",
    )
    test_db.record_posted_offer(
        offer_key="ml:MLB555444",
        title="Monitor Gamer LG UltraGear 27 IPS",
        price=899.00,
        original_price=1399.00,
        topic_key="tech_celulares",
        affiliate_url="https://mercadolivre.com/sec/lg27",
        target_chat_id=-10033,
        message_id=501,
    )
    hist_points = test_db.get_offer_price_points("Monitor Gamer LG")
    assert len(hist_points) >= 2
    png_bytes = generate_price_history_card(hist_points[-1]["title"], hist_points)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    showcase_payload = build_showcase_api_payload(database=test_db, search_query="Monitor")
    assert showcase_payload["count"] == 1
    assert showcase_payload["offers"][0]["price"] == 999.00

    test_db.mark_posted_offer_expired("ml:MLB555444")
    to_delete = test_db.get_expired_offers_for_deletion(older_than_hours=0)
    assert len(to_delete) == 1
    assert to_delete[0]["target_chat_id"] == -10033
    test_db.mark_posted_offer_deleted("ml:MLB555444")
    assert len(test_db.get_expired_offers_for_deletion(older_than_hours=0)) == 0

    assert is_quiet_hours(datetime(2026, 11, 23, 23, 45)) is True
    assert is_quiet_hours(datetime(2026, 11, 23, 14, 0)) is False
    assert extract_unit_hint("Kit 4 Pilhas Recarregáveis Eneloop", 80.0) is not None
    assert build_title_signature("Smartphone Samsung Galaxy S24 256GB") == build_title_signature("Celular Samsung Galaxy S24 256GB")

    payload = {"url": "https://produto.mercadolivre.com.br/MLB-123-item-_JM?matt_tool=999"}
    b64_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    assert extract_pelando_jwt_url(f"https://dpl.pelando.com.br/r/eyJ.{b64_payload}.sig") == payload["url"]
    assert extract_mlb_code("https://www.mercadolivre.com.br/up/MLBU3182315457") == "MLBU3182315457"
    assert is_aggregator_url("https://www.promobit.com.br/Redirect/to/2402292/") is True

    rep_html = format_operational_report(test_db.get_24h_operational_report())
    assert "RELATÓRIO OPERACIONAL 24H" in rep_html
    top5_html = format_daily_top5_summary([{"title": "Monitor LG 27", "price": 899.0, "discount_pct": 36, "affiliate_url": "https://mercadolivre.com/sec/lg27"}])
    assert "TOP 5 MELHORES OFERTAS DO DIA" in top5_html

    panel_text, panel_kb = _build_admin_panel_view()
    assert "PAINEL DE CONTROLE DO ADMINISTRADOR" in panel_text
    assert len(panel_kb.inline_keyboard) == 4
    draft_kb = _build_draft_preview_keyboard("abc12345")
    assert len(draft_kb.inline_keyboard) == 2
