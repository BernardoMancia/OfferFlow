from __future__ import annotations

import html
import re
from typing import Any, Dict, Optional

from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import OFFICIAL_TOPICS, TOPIC_EMOJIS, settings


def format_brl(value: Optional[float]) -> str:

    if value is None or value <= 0:
        return "R$ 0,00"
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def extract_unit_hint(
    title: str, price: float, topic_key: str = ""
) -> Optional[str]:
\
\
\

    if price <= 0 or not title:
        return None


    kit_match = re.search(
        r"\b(?:kit|pack|caixa\s+com|c/)\s*(\d{2,3}|\d)\s*(?:un|unis|unidades|barras|pacotes|latas)?\b",
        title,
        flags=re.IGNORECASE,
    )
    if kit_match:
        qty = int(kit_match.group(1))
        if 2 <= qty <= 200:
            unit_price = price / qty
            return f"💡 <i>Sai a {format_brl(unit_price)} por unidade</i>"


    if topic_key in ("doces_importados", "comidas_importadas"):

        g_match = re.search(
            r"\b(\d{2,4})\s*(?:g|gr|gramas)\b", title, flags=re.IGNORECASE
        )
        if g_match:
            grams = int(g_match.group(1))
            if 50 <= grams <= 5000:
                per_100g = (price / grams) * 100.0
                return f"⚖️ <i>Equivale a {format_brl(per_100g)} a cada 100g</i>"


        ml_match = re.search(
            r"\b(\d{3,4})\s*ml\b", title, flags=re.IGNORECASE
        )
        if ml_match:
            ml = int(ml_match.group(1))
            if 200 <= ml <= 5000:
                per_liter = (price / ml) * 1000.0
                return f"🍾 <i>Sai a {format_brl(per_liter)} por Litro</i>"


        l_match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:l|litros)\b", title, flags=re.IGNORECASE
        )
        if l_match:
            liters = float(l_match.group(1).replace(",", "."))
            if 1.0 < liters <= 20.0:
                per_liter = price / liters
                return f"🍾 <i>Sai a {format_brl(per_liter)} por Litro</i>"

    return None


def format_offer_message(
    offer: Dict[str, Any], is_historical_low: bool = False
) -> str:
\
\
\
\
\
\
\
\
\
\
\

    topic_key = str(offer.get("topic_key") or "bugs_imperdiveis")
    emoji = TOPIC_EMOJIS.get(topic_key, "🔥")

    raw_title = str(offer.get("title") or "Oferta em Destaque").strip()
    safe_title = html.escape(raw_title)

    store = html.escape(str(offer.get("store") or "Mercado Livre").strip())
    is_full = bool(offer.get("is_full"))
    full_badge = " ⚡ <b>Full</b>" if is_full else ""

    price = float(offer.get("price") or 0.0)
    original_price = offer.get("original_price")
    original_price_val = float(original_price) if original_price else 0.0

    discount_pct = int(offer.get("discount_pct") or 0)
    if discount_pct <= 0 and original_price_val > price > 0:
        discount_pct = round(((original_price_val - price) / original_price_val) * 100)

    lines = [
        f"{emoji} <b>{safe_title}</b>",
        "",
        f"🏪 <b>Loja:</b> {store}{full_badge}",
    ]

    rating = offer.get("rating")
    if rating and float(rating) > 0:
        rat_val = float(rating)
        rev_cnt = int(offer.get("reviews_count") or 0)
        rev_str = f" <i>({rev_cnt:,} avaliações)</i>".replace(",", ".") if rev_cnt > 0 else ""
        lines.append(f"⭐ <b>Avaliação:</b> {rat_val:.1f}/5.0{rev_str}")

    if original_price_val > price > 0:
        lines.append(f"❌ <b>De:</b> <s>{format_brl(original_price_val)}</s>")

    discount_suffix = f" <b>({discount_pct}% OFF)</b>" if discount_pct > 0 else ""
    lines.append(f"🔥 <b>Por:</b> <b>{format_brl(price)}</b>{discount_suffix}")

    installments = offer.get("installments")
    if installments and str(installments).strip():
        safe_inst = html.escape(str(installments).strip())
        lines.append(f"💳 <b>Parcelamento:</b> <i>{safe_inst}</i>")

    unit_hint = extract_unit_hint(raw_title, price, topic_key=topic_key)
    if unit_hint:
        lines.append(unit_hint)

    if is_historical_low or bool(offer.get("is_historical_low")):
        savings_vs_low = float(offer.get("savings_vs_low") or 0.0)
        if savings_vs_low >= 1.0:
            lines.append(
                f"📉 <b>Menor preço já registrado no grupo!</b> <i>({format_brl(savings_vs_low)} abaixo do recorde anterior)</i>"
            )
        else:
            lines.append("📉 <b>Menor preço já registrado no grupo!</b>")

    coupon = offer.get("coupon")
    if coupon and str(coupon).strip():
        raw_coupon = str(coupon).strip()
        safe_coupon = html.escape(raw_coupon)
        if "com cupom" in raw_coupon.lower() or "% off" in raw_coupon.lower():
            lines.append(
                f"🎟️ <b>Cupom na página:</b> <i>{safe_coupon} (ative no anúncio)</i>"
            )
        else:
            lines.append(
                f"🎟️ <b>Cupom:</b> <code>{safe_coupon}</code> <i>(toque no código para copiar)</i>"
            )

    lines.append("")
    lines.append(
        "⚠️ <i>Promoção sujeita a alteração de preço ou estoque a qualquer momento.</i>"
    )

    return "\n".join(lines)


def format_daily_top5_summary(offers: list[Dict[str, Any]]) -> str:
\
\
\

    lines = [
        "🏆 <b>TOP 5 MELHORES PROMOÇÕES DO DIA!</b> 🔥",
        "<i>Perdeu as postagens de hoje? Confira os maiores descontos das últimas 24h:</i>",
        "",
    ]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(offers[:5]):
        medal = medals[idx] if idx < len(medals) else "🔹"
        title = html.escape(str(item.get("title") or "Oferta")[:68])
        price = format_brl(float(item.get("price") or 0.0))
        disc = int(item.get("discount_pct") or 0)
        disc_str = f" <b>(-{disc}%)</b>" if disc > 0 else ""
        url = html.escape(str(item.get("affiliate_url") or ""))
        store = html.escape(str(item.get("store") or "Mercado Livre"))
        lines.append(
            f"{medal} <b>{title}</b>\n"
            f"   💰 Por: <b>{price}</b>{disc_str} ({store}) — <a href=\"{url}\">🛒 Pegar Oferta</a>"
        )
        lines.append("")

    lines.append("⚠️ <i>Preços e estoques sujeitos a alteração a qualquer momento.</i>")
    return "\n".join(lines)


def format_operational_report(report: Dict[str, Any]) -> str:
\
\

    by_source = report.get("24h_by_source") or {}
    sent_by_topic = report.get("24h_sent_by_topic") or {}
    sent_by_store = report.get("24h_sent_by_store") or {}
    pending_by_topic = report.get("pending_by_topic") or {}

    lines = [
        "📊 <b>RELATÓRIO OPERACIONAL (ÚLTIMAS 24H)</b>",
        "",
        f"📤 <b>Publicadas nas últimas 24h:</b> <b>{report.get('24h_sent_total', 0)}</b>",
        f"📥 <b>Pendentes na fila agora:</b> <b>{report.get('pending_queue', 0)}</b>",
        f"⚡ <b>Barradas no Just-in-Time (esgotadas/subiram):</b> <b>{report.get('24h_jit_discarded', 0)}</b>",
        f"🔴 <b>Bugs marcados como encerrados:</b> <b>{report.get('24h_expired_detected', 0)}</b>",
        f"🗄️ <b>Total histórico publicado:</b> <b>{report.get('posted_total', 0)}</b>",
        "",
        "🛰️ <b>Coleta por Fonte (24h):</b>",
    ]
    if by_source:
        for src, cnt in by_source.items():
            lines.append(f"• <code>{html.escape(str(src))}</code>: <b>{cnt}</b> aprovadas")
    else:
        lines.append("• <i>Nenhuma coleta registrada nas últimas 24h</i>")

    lines.append("")
    lines.append("📂 <b>Envios e Fila por Tópico:</b>")
    for t_key, t_name in OFFICIAL_TOPICS.items():
        s_cnt = sent_by_topic.get(t_key, 0)
        p_cnt = pending_by_topic.get(t_key, 0)
        lines.append(f"• {t_name}: <b>{s_cnt}</b> enviadas | <b>{p_cnt}</b> na fila")

    if sent_by_store:
        lines.append("")
        lines.append("🏪 <b>Lojas Publicadas (24h):</b>")
        for st, cnt in sent_by_store.items():
            lines.append(f"• {html.escape(str(st))}: <b>{cnt}</b>")

    return "\n".join(lines)


def build_offer_keyboard(offer: Dict[str, Any]) -> InlineKeyboardMarkup:
\
\
\
\

    store = str(offer.get("store") or "Mercado Livre").strip()
    affiliate_url = str(
        offer.get("affiliate_url") or offer.get("original_url") or ""
    ).strip()

    prep = "no" if store.lower() in ("mercado livre", "aliexpress") else "na"
    button_text = f"🛒 Pegar Promoção {prep} {store}"

    title = str(offer.get("title") or "Promoção Imperdível").strip()
    price = format_brl(float(offer.get("price") or 0.0))
    share_text = f"🔥 {title} por {price}!"
    if settings.telegram_group_invite_url:
        share_text += f"\n📲 Mais promoções em: {settings.telegram_group_invite_url}"
    share_url = f"https://t.me/share/url?url={quote(affiliate_url)}&text={quote(share_text)}"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text=button_text, url=affiliate_url),
                InlineKeyboardButton(text="📤 Compartilhar", url=share_url),
            ]
        ]
    )
