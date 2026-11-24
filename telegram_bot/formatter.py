from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from classifier.catalogs import (
    BOT_BRAND_NAME,
    CHANNEL_CATALOG,
    HUB_CHANNEL_SPEC,
    OFFICIAL_TOPICS,
    TOPIC_EMOJIS,
)
from config import settings


def format_brl(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "R$ 0,00"
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def extract_unit_hint(
    title: str, price: float, topic_key: str = ""
) -> Optional[str]:
    if price <= 0 or not title:
        return None

    kit_match = re.search(
        r"\b(?:kit|pack|caixa\s+com|c/)\s*(\d{2,3}|\d)\s*(?:un|unis|unidades|pecas|peças|pares|pacotes)?\b",
        title,
        flags=re.IGNORECASE,
    )
    if kit_match:
        qty = int(kit_match.group(1))
        if 2 <= qty <= 200:
            unit_price = price / qty
            return f"💡 <i>Sai a {format_brl(unit_price)} por unidade</i>"

    return None


def format_offer_message(
    offer: Dict[str, Any], is_historical_low: bool = False
) -> str:
    topic_key = str(offer.get("topic_key") or "ofertas_bugs")
    cat_spec = CHANNEL_CATALOG.get(topic_key) or {}
    cat_label = str(cat_spec.get("short_name") or OFFICIAL_TOPICS.get(topic_key, "Oferta Mercado Livre")).upper()
    emoji = TOPIC_EMOJIS.get(topic_key, "🔥")

    raw_title = str(offer.get("title") or "Oferta em Destaque").strip()
    safe_title = html.escape(raw_title)

    price = float(offer.get("price") or 0.0)
    original_price = offer.get("original_price")
    original_price_val = float(original_price) if original_price else 0.0

    discount_pct = int(offer.get("discount_pct") or 0)
    if discount_pct <= 0 and original_price_val > price > 0:
        discount_pct = round(((original_price_val - price) / original_price_val) * 100)

    if topic_key == "ofertas_bugs" or discount_pct >= 50:
        header = f"🚨 <b>{html.escape(cat_label)}</b>  •  <code>SUPER DESCONTO</code>"
    else:
        header = f"✨ <b>{html.escape(cat_label)}</b>  •  <code>OFERTA VERIFICADA</code>"

    lines = [
        header,
        "",
        f"{emoji} <b>{safe_title}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if original_price_val > price > 0:
        lines.append(f"❌ De: <s>{format_brl(original_price_val)}</s>")

    discount_suffix = f"  <b>(-{discount_pct}% OFF)</b>" if discount_pct > 0 else ""
    lines.append(f"🔥 <b>Por: {format_brl(price)}</b>{discount_suffix}")

    installments = offer.get("installments")
    if installments and str(installments).strip():
        safe_inst = html.escape(str(installments).strip())
        lines.append(f"💳 <i>{safe_inst}</i>")

    unit_hint = extract_unit_hint(raw_title, price, topic_key=topic_key)
    if unit_hint:
        lines.append(unit_hint)

    if is_historical_low or bool(offer.get("is_historical_low")):
        savings_vs_low = float(offer.get("savings_vs_low") or 0.0)
        if savings_vs_low >= 1.0:
            lines.append(
                f"📉 <b>Menor preço histórico!</b> <i>({format_brl(savings_vs_low)} abaixo do recorde)</i>"
            )
        else:
            lines.append("📉 <b>Menor preço histórico registrado!</b>")

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    trust_badges: List[str] = []
    seller_rep = str(offer.get("seller_reputation") or "").strip().lower()
    if seller_rep == "green":
        trust_badges.append("🏅 <b>Vendedor Verde</b>")
    elif seller_rep == "yellow":
        trust_badges.append("🟡 <b>Vendedor Amarelo</b>")
    else:
        trust_badges.append("🏪 <b>Mercado Livre</b>")

    if bool(offer.get("is_full")):
        trust_badges.append("⚡ <b>Envio FULL</b>")

    cond = str(offer.get("condition") or "new").strip().lower()
    if cond == "refurbished":
        trust_badges.append("♻️ <b>Recondicionado</b>")
    else:
        trust_badges.append("📦 <b>Novo</b>")

    lines.append("")
    lines.append("  •  ".join(trust_badges))

    rating = offer.get("rating")
    if rating and float(rating) > 0:
        rat_val = float(rating)
        rev_cnt = int(offer.get("reviews_count") or 0)
        rev_str = f" <i>({rev_cnt:,} avaliações)</i>".replace(",", ".") if rev_cnt > 0 else ""
        lines.append(f"⭐ <b>{rat_val:.1f}/5.0</b>{rev_str}")

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
                f"🎟️ <b>Cupom:</b> <code>{safe_coupon}</code> <i>(toque para copiar)</i>"
            )

    lines.append("")
    lines.append(
        f"⚡ <i>Curadoria {BOT_BRAND_NAME} • Preço e estoque sujeitos a alteração.</i>"
    )

    return "\n".join(lines)


def build_offer_keyboard(
    offer: Dict[str, Any],
    hub_url: Optional[str] = None,
) -> InlineKeyboardMarkup:
    affiliate_url = str(
        offer.get("affiliate_url") or offer.get("original_url") or ""
    ).strip()

    title = str(offer.get("title") or "Promoção Imperdível").strip()
    price = format_brl(float(offer.get("price") or 0.0))
    share_text = f"🔥 {title} por {price} no Mercado Livre!"
    community_link = (hub_url or settings.telegram_group_invite_url or "").strip()
    if community_link:
        share_text += f"\n⚡ Mais ofertas na Comunidade {BOT_BRAND_NAME}: {community_link}"
    share_url = f"https://t.me/share/url?url={quote(affiliate_url)}&text={quote(share_text)}"

    row_main = [
        InlineKeyboardButton(text="🛒 Garantir no Mercado Livre", url=affiliate_url),
    ]
    row_secondary = [
        InlineKeyboardButton(text="📤 Compartilhar", url=share_url),
    ]
    if community_link.startswith("http"):
        row_secondary.append(
            InlineKeyboardButton(text=f"⚡ Comunidade {BOT_BRAND_NAME}", url=community_link)
        )

    return InlineKeyboardMarkup([row_main, row_secondary])


def format_hub_directory_message(
    channels: List[Dict[str, Any]],
    folder_url: str = "",
) -> str:
    lines = [HUB_CHANNEL_SPEC["welcome_text"], ""]

    linked_count = 0
    for ch in channels:
        cat_key = str(ch.get("category_key") or "")
        if cat_key == "hub":
            continue
        spec = CHANNEL_CATALOG.get(cat_key) or {}
        short_name = spec.get("short_name", cat_key)
        emoji = spec.get("emoji", "📌")
        if ch.get("chat_id"):
            linked_count += 1
            url = ch.get("invite_url") or (
                f"https://t.me/{ch['username']}" if ch.get("username") else ""
            )
            if url:
                lines.append(f"{emoji} <a href=\"{html.escape(url)}\"><b>{html.escape(short_name)}</b></a>")
            else:
                lines.append(f"{emoji} <b>{html.escape(short_name)}</b> <i>(ativo)</i>")

    if linked_count == 0:
        lines.append("<i>Os canais de categorias estão sendo conectados à comunidade...</i>")

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "🔔 <b>Quer alertas personalizados no privado?</b>",
            "Abra o <b>OfferFlow Assistente</b> e envie <code>/alerta rtx 4060 1900</code> ou <code>/historico airfryer</code>!",
        ]
    )
    if folder_url:
        lines.append("")
        lines.append("📂 <b>Dica:</b> Clique no botão abaixo para adicionar <b>todos os canais de uma vez</b> em uma Pasta do Telegram!")
    return "\n".join(lines)


def build_hub_directory_keyboard(
    channels: List[Dict[str, Any]],
    folder_url: str = "",
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    if folder_url and folder_url.startswith("http"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="📂 Adicionar Pasta Completa (Todos os Canais)",
                    url=folder_url,
                )
            ]
        )

    cat_buttons: List[InlineKeyboardButton] = []
    for ch in channels:
        cat_key = str(ch.get("category_key") or "")
        if cat_key == "hub" or not ch.get("chat_id"):
            continue
        url = ch.get("invite_url") or (
            f"https://t.me/{ch['username']}" if ch.get("username") else ""
        )
        if not url or not str(url).startswith("http"):
            continue
        spec = CHANNEL_CATALOG.get(cat_key) or {}
        emoji = spec.get("emoji", "📌")
        short_name = str(spec.get("short_name") or cat_key)[:26]
        cat_buttons.append(InlineKeyboardButton(text=f"{emoji} {short_name}", url=str(url)))

    for i in range(0, len(cat_buttons), 2):
        rows.append(cat_buttons[i : i + 2])

    return InlineKeyboardMarkup(rows)


def format_daily_top5_summary(offers: list[Dict[str, Any]]) -> str:
    lines = [
        f"🏆 <b>TOP 5 MELHORES OFERTAS DO DIA • {BOT_BRAND_NAME.upper()}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "<i>Perdeu os achados de hoje? Confira os maiores descontos verificados no Mercado Livre:</i>",
        "",
    ]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(offers[:5]):
        medal = medals[idx] if idx < len(medals) else "🔹"
        title = html.escape(str(item.get("title") or "Oferta")[:68])
        price = format_brl(float(item.get("price") or 0.0))
        disc = int(item.get("discount_pct") or 0)
        disc_str = f" <b>(-{disc}% OFF)</b>" if disc > 0 else ""
        url = html.escape(str(item.get("affiliate_url") or ""))
        lines.append(
            f"{medal} <b>{title}</b>\n"
            f"   🔥 Por: <b>{price}</b>{disc_str} — <a href=\"{url}\">🛒 Garantir no ML</a>"
        )
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(
        f"⚡ <i>Curadoria 100% Mercado Livre • {BOT_BRAND_NAME}</i>"
    )
    return "\n".join(lines)


def format_operational_report(report: Dict[str, Any]) -> str:
    by_source = report.get("24h_by_source") or {}
    sent_by_topic = report.get("24h_sent_by_topic") or {}
    pending_by_topic = report.get("pending_by_topic") or {}

    lines = [
        f"📊 <b>RELATÓRIO OPERACIONAL 24H • {BOT_BRAND_NAME.upper()}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📤 <b>Publicadas (24h):</b> <b>{report.get('24h_sent_total', 0)}</b>",
        f"📥 <b>Pendentes na fila:</b> <b>{report.get('pending_queue', 0)}</b>",
        f"📢 <b>Canais vinculados:</b> <b>{report.get('linked_channels', 0)}/{report.get('total_channels', 8)}</b> | Hub: {'✅' if report.get('hub_linked') else '⚠️'}",
        f"⚡ <b>Barradas no Just-in-Time:</b> <b>{report.get('24h_jit_discarded', 0)}</b>",
        f"🔴 <b>Encerradas detectadas:</b> <b>{report.get('24h_expired_detected', 0)}</b>",
        f"🗄️ <b>Total histórico publicado:</b> <b>{report.get('posted_total', 0)}</b>",
        "",
        "🛰️ <b>Coleta por Frente (24h):</b>",
    ]
    if by_source:
        for src, cnt in by_source.items():
            lines.append(f"• <code>{html.escape(str(src))}</code>: <b>{cnt}</b> aprovadas")
    else:
        lines.append("• <i>Nenhuma coleta registrada nas últimas 24h</i>")

    lines.append("")
    lines.append("📂 <b>Envios e Fila por Canal (8 Categorias ML):</b>")
    for t_key, t_name in OFFICIAL_TOPICS.items():
        s_cnt = sent_by_topic.get(t_key, 0)
        p_cnt = pending_by_topic.get(t_key, 0)
        lines.append(f"• {t_name}: <b>{s_cnt}</b> enviadas | <b>{p_cnt}</b> na fila")

    return "\n".join(lines)
