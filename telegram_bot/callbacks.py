from __future__ import annotations

import asyncio
import html
import re
import uuid
from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from affiliate.mercadolivre import convert_to_affiliate_url
from affiliate.url_cleaner import extract_offer_key
from classifier.topic_router import classify_offer_topic
from config import OFFICIAL_TOPICS, TOPIC_EMOJIS
from core.scheduler import (
    job_scrape_aggregators,
    job_scrape_ml_imported_hunter,
    job_scrape_ml_offers,
)
from database.db import db
from scrapers.ml_offers import scrape_single_product_url
from telegram_bot.admin_handlers import (
    _build_admin_panel_view,
    _get_delete_expired_hours,
)
from telegram_bot.formatter import format_offer_message, format_operational_report
from telegram_bot.member_handlers import _build_user_alerts_view
from telegram_bot.publisher import publish_daily_top5_summary, publish_offer
from telegram_bot.setup_topics import is_user_admin


def _build_draft_preview_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Publicar Agora", callback_data=f"draft:pub:{draft_id}"),
                InlineKeyboardButton("📥 Colocar na Fila", callback_data=f"draft:queue:{draft_id}"),
            ],
            [
                InlineKeyboardButton("🔄 Trocar Tópico", callback_data=f"draft:topic:{draft_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data=f"draft:cancel:{draft_id}"),
            ],
        ]
    )


async def handle_admin_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    data = str(query.data or "")

    if data.startswith("rmalert:"):
        alert_id = int(data.split(":", 1)[1])
        ok = db.remove_user_alert(user.id, alert_id)
        await query.answer(
            f"🗑️ Alerta #{alert_id} removido!" if ok else "Alerta já removido."
        )
        text, kb = _build_user_alerts_view(user.id)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except TelegramError:
            pass
        return

    configured_group_id = db.get_chat_id()
    if not configured_group_id or not await is_user_admin(
        context.bot, int(configured_group_id), user.id
    ):
        await query.answer("⛔ Acesso exclusivo para Administradores.", show_alert=True)
        return

    if data.startswith("panel:"):
        action = data.split(":", 1)[1]
        if action == "pause":
            db.set_paused(True)
            await query.answer("⏸️ Publicação automática pausada!")
            text, kb = _build_admin_panel_view()
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif action == "resume":
            db.set_paused(False)
            await query.answer("▶️ Publicação automática retomada!")
            text, kb = _build_admin_panel_view()
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif action == "toggle_del_exp":
            cur_val = _get_delete_expired_hours()
            if cur_val > 0:
                next_val = 0
                msg_toast = "🗑️ Auto-limpeza ajustada para IMEDIATA (0h)!"
            elif cur_val == 0:
                next_val = -1
                msg_toast = "📌 Auto-limpeza DESATIVADA (mantém aviso tachado)!"
            else:
                next_val = 12
                msg_toast = "🧹 Auto-limpeza ativada para após 12 horas!"
            db.set_config("delete_expired_after_hours", str(next_val))
            await query.answer(msg_toast, show_alert=True)
            text, kb = _build_admin_panel_view()
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif action == "refresh":
            await query.answer("🔄 Painel atualizado!")
            text, kb = _build_admin_panel_view()
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except TelegramError:
                pass
        elif action == "report":
            await query.answer("📊 Gerando relatório 24h...")
            rep_html = format_operational_report(db.get_24h_operational_report())
            back_kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data="panel:refresh")]]
            )
            await query.edit_message_text(rep_html, parse_mode=ParseMode.HTML, reply_markup=back_kb)
        elif action == "top5":
            ok = await publish_daily_top5_summary(context.bot, database=db)
            await query.answer(
                "🏆 Resumo Top 5 publicado!" if ok else "ℹ️ Sem ofertas suficientes nas últimas 24h.",
                show_alert=True,
            )
        elif action == "clear":
            removed = db.clear_pending_queue()
            await query.answer(f"🧹 {removed} ofertas removidas da fila!", show_alert=True)
            text, kb = _build_admin_panel_view()
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif action == "scan":
            await query.answer("🔍 Iniciando varredura nas 3 frentes...")
            await query.edit_message_text(
                "⏳ <b>Executando varredura nas 3 frentes (Agregadores, Ofertas ML e Caçador de Importados)...</b>",
                parse_mode=ParseMode.HTML,
            )
            c1, c2, c3 = await asyncio.gather(
                job_scrape_ml_imported_hunter(),
                job_scrape_ml_offers(),
                job_scrape_aggregators(),
            )
            text, kb = _build_admin_panel_view()
            summary = (
                f"✅ <b>Varredura concluída (+{c1 + c2 + c3} na fila)!</b>\n\n" + text
            )
            await query.edit_message_text(summary, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif action == "queue":
            await query.answer()
            items = db.list_pending_queue(limit=8)
            if not items:
                back_kb = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data="panel:refresh")]]
                )
                await query.edit_message_text(
                    "📭 <b>A fila está vazia no momento.</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_kb,
                )
                return
            lines = ["📋 <b>Gerenciar Próximas Ofertas da Fila:</b>", ""]
            rows_kb: List[List[InlineKeyboardButton]] = []
            for it in items:
                qid = int(it["id"])
                emoji = TOPIC_EMOJIS.get(it["topic_key"], "🔥")
                title_short = html.escape(str(it["title"])[:45])
                lines.append(
                    f"<b>#{qid}</b> {emoji} <b>R$ {float(it['price']):.2f}</b> — {title_short}"
                )
                rows_kb.append(
                    [
                        InlineKeyboardButton(
                            f"🗑️ Remover #{qid} ({str(it['title'])[:24]}...)",
                            callback_data=f"rmq:{qid}",
                        )
                    ]
                )
            rows_kb.append([InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data="panel:refresh")])
            await query.edit_message_text(
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(rows_kb),
            )
        return

    if data.startswith("rmq:"):
        qid = int(data.split(":", 1)[1])
        ok = db.remove_queue_item(qid)
        await query.answer(f"🗑️ Oferta #{qid} removida!" if ok else "Item já removido.")
        query.data = "panel:queue"
        await handle_admin_callback(update, context)
        return

    if data.startswith("draft:"):
        parts = data.split(":")
        action = parts[1]
        draft_id = parts[2]
        drafts: Dict[str, Dict[str, Any]] = context.application.bot_data.setdefault("drafts", {})
        offer_payload = drafts.get(draft_id)
        if not offer_payload:
            await query.answer("⚠️ Esta prévia já expirou ou foi processada.", show_alert=True)
            return

        if action == "cancel":
            drafts.pop(draft_id, None)
            await query.answer("❌ Envio cancelado.")
            await query.edit_message_text(
                "❌ <b>Publicação cancelada pelo Administrador.</b>",
                parse_mode=ParseMode.HTML,
            )
        elif action == "topic":
            await query.answer("Escolha o tópico de destino:")
            topic_buttons: List[List[InlineKeyboardButton]] = []
            for t_key, t_name in OFFICIAL_TOPICS.items():
                topic_buttons.append(
                    [InlineKeyboardButton(t_name, callback_data=f"draft:settopic:{draft_id}:{t_key}")]
                )
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(topic_buttons))
        elif action == "settopic" and len(parts) >= 4:
            new_topic = parts[3]
            offer_payload["topic_key"] = new_topic
            topic_label = OFFICIAL_TOPICS.get(new_topic, new_topic)
            await query.answer(f"📂 Tópico alterado para: {topic_label}")
            preview_header = (
                f"👁️ <b>PRÉVIA DA OFERTA</b>\n"
                f"📂 <b>Tópico:</b> {topic_label}\n"
                f"🔗 <b>Afiliado:</b> <code>{html.escape(str(offer_payload['affiliate_url']))}</code>\n"
                f"──────────────────────\n"
            )
            await query.edit_message_text(
                preview_header + format_offer_message(offer_payload),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=_build_draft_preview_keyboard(draft_id),
            )
        elif action == "queue":
            drafts.pop(draft_id, None)
            qid = db.enqueue_offer(
                offer_key=offer_payload["offer_key"],
                title=offer_payload["title"],
                price=offer_payload["price"],
                original_price=offer_payload.get("original_price"),
                discount_pct=offer_payload.get("discount_pct", 0),
                coupon=offer_payload.get("coupon"),
                installments=offer_payload.get("installments"),
                store=offer_payload.get("store", "Mercado Livre"),
                is_full=bool(offer_payload.get("is_full")),
                image_url=offer_payload.get("image_url"),
                affiliate_url=offer_payload["affiliate_url"],
                original_url=offer_payload.get("original_url"),
                topic_key=offer_payload["topic_key"],
                source="manual_admin",
                rating=offer_payload.get("rating"),
                reviews_count=offer_payload.get("reviews_count"),
            )
            await query.answer("📥 Adicionada na fila!")
            topic_label = OFFICIAL_TOPICS.get(offer_payload["topic_key"], offer_payload["topic_key"])
            await query.edit_message_text(
                f"📥 <b>Oferta enfileirada com sucesso em [{topic_label}] (Fila #{qid or 'atualizada'})!</b>",
                parse_mode=ParseMode.HTML,
            )
        elif action == "pub":
            drafts.pop(draft_id, None)
            await query.answer("🚀 Publicando no grupo...")
            ok = await publish_offer(context.bot, offer_payload, database=db)
            if ok:
                db.record_posted_offer(
                    offer_key=offer_payload["offer_key"],
                    title=offer_payload["title"],
                    price=offer_payload["price"],
                    topic_key=offer_payload["topic_key"],
                    original_price=offer_payload.get("original_price"),
                    affiliate_url=offer_payload["affiliate_url"],
                    original_url=offer_payload.get("original_url"),
                    message_id=offer_payload.get("_sent_message_id"),
                    thread_id=offer_payload.get("_sent_thread_id"),
                    has_photo=bool(offer_payload.get("_sent_has_photo")),
                    caption_html=offer_payload.get("_sent_caption_html"),
                )
                topic_label = OFFICIAL_TOPICS.get(offer_payload["topic_key"], offer_payload["topic_key"])
                await query.edit_message_text(
                    f"✅ <b>Oferta publicada imediatamente em [{topic_label}]!</b>\n"
                    f"📦 <b>Produto:</b> {html.escape(str(offer_payload['title'])[:70])}\n"
                    f"🔗 <b>Link Afiliado:</b> <code>{html.escape(str(offer_payload['affiliate_url']))}</code>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.edit_message_text(
                    "❌ <b>Falha ao publicar oferta no grupo.</b> Verifique o <code>/status</code>.",
                    parse_mode=ParseMode.HTML,
                )


async def handle_private_message_guard(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if not chat or not message or chat.type != ChatType.PRIVATE:
        return

    configured_group_id = db.get_chat_id()
    if not configured_group_id or not user or not await is_user_admin(
        context.bot, int(configured_group_id), user.id
    ):
        try:
            await message.reply_text(
                "⛔ <b>Acesso Restrito:</b> Este Bot é exclusivo para os Administradores do grupo oficial.",
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass
        return

    db.set_config("admin_private_chat_id", str(chat.id))
    text = (message.text or message.caption or "").strip()
    url_match = re.search(r"(https?://[^\s<>\"']+)", text)
    if not url_match:
        await message.reply_text(
            "👋 <b>Olá, Administrador!</b>\n\n"
            "• Cole qualquer <b>link de produto</b> (Mercado Livre, Amazon, Shopee, Magalu) aqui para gerar uma prévia interativa.\n"
            "• Ou abra o <code>/painel</code> para gerenciar o Bot.",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_url = url_match.group(1).strip()
    remaining_text = (text[: url_match.start()] + " " + text[url_match.end() :]).strip()
    coupon = remaining_text if 2 <= len(remaining_text) <= 25 else None

    status_msg = await message.reply_text(
        "⏳ <b>Extraindo produto e montando prévia interativa...</b>",
        parse_mode=ParseMode.HTML,
    )

    scraped = await scrape_single_product_url(raw_url, coupon=coupon)
    if not scraped:
        await status_msg.edit_text(
            "❌ <b>Não foi possível extrair título/preço deste link automaticamente.</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    affiliate_url = await convert_to_affiliate_url(scraped.url)
    topic_key = (
        classify_offer_topic(
            title=scraped.title,
            discount_pct=scraped.discount_pct,
            coupon=scraped.coupon,
            price=scraped.price,
        )
        or "bugs_imperdiveis"
    )
    offer_key = extract_offer_key(scraped.url, scraped.title)

    draft_id = uuid.uuid4().hex[:10]
    offer_payload: Dict[str, Any] = {
        "offer_key": offer_key,
        "title": scraped.title,
        "price": scraped.price,
        "original_price": scraped.original_price,
        "discount_pct": scraped.discount_pct,
        "coupon": scraped.coupon,
        "installments": scraped.installments,
        "store": scraped.store,
        "is_full": scraped.is_full,
        "image_url": scraped.image_url,
        "affiliate_url": affiliate_url,
        "original_url": scraped.url,
        "topic_key": topic_key,
        "rating": scraped.rating,
        "reviews_count": scraped.reviews_count,
    }
    drafts = context.application.bot_data.setdefault("drafts", {})
    drafts[draft_id] = offer_payload

    topic_label = OFFICIAL_TOPICS.get(topic_key, topic_key)
    preview_header = (
        f"👁️ <b>PRÉVIA DA OFERTA</b>\n"
        f"📂 <b>Tópico sugerido:</b> {topic_label}\n"
        f"🔗 <b>Afiliado:</b> <code>{html.escape(affiliate_url)}</code>\n"
        f"──────────────────────\n"
    )
    await status_msg.edit_text(
        preview_header + format_offer_message(offer_payload),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=_build_draft_preview_keyboard(draft_id),
    )
