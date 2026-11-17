from __future__ import annotations

import asyncio
import html
from typing import Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from affiliate.mercadolivre import convert_to_affiliate_url
from affiliate.url_cleaner import extract_offer_key
from classifier.topic_router import classify_offer_topic
from config import OFFICIAL_TOPICS, settings
from core.scheduler import (
    job_scrape_aggregators,
    job_scrape_ml_imported_hunter,
    job_scrape_ml_offers,
)
from database.db import db
from scrapers.ml_offers import scrape_single_product_url
from telegram_bot.formatter import format_operational_report
from telegram_bot.publisher import (
    is_quiet_hours,
    publish_daily_top5_summary,
    publish_offer,
)
from telegram_bot.setup_topics import is_user_admin, lock_group_for_non_admins

_AFFILIATE_CONFIG_KEYS: Dict[str, str] = {
    "ml_matt_tool": "Mercado Livre matt_tool",
    "ml_matt_word": "Mercado Livre matt_word",
    "ml_affiliate_tag": "Mercado Livre Tag (/sec/)",
    "amazon_affiliate_tag": "Amazon Associate Tag",
    "shopee_affiliate_id": "Shopee Affiliate ID",
    "magalu_store_slug": "Vitrine Parceiro Magalu",
}


async def _check_command_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if not chat or not message:
        return False

    configured_group_id = db.get_chat_id()
    check_group_id = (
        chat.id if chat.type == ChatType.SUPERGROUP else configured_group_id
    )

    if (
        chat.type == ChatType.SUPERGROUP
        and message.sender_chat
        and message.sender_chat.id == chat.id
    ):
        return True

    if check_group_id and user and await is_user_admin(context.bot, int(check_group_id), user.id):
        if chat.type == ChatType.PRIVATE:
            db.set_config("admin_private_chat_id", str(chat.id))
        return True

    if chat.type == ChatType.SUPERGROUP:
        try:
            await message.delete()
        except TelegramError:
            pass
        await lock_group_for_non_admins(context.bot, chat.id)
    else:
        try:
            await message.reply_text(
                "⛔ <b>Acesso Negado:</b> Apenas Administradores do grupo oficial podem utilizar comandos ou enviar links neste Bot.",
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass

    return False


def _get_delete_expired_hours() -> int:
    raw = db.get_config("delete_expired_after_hours")
    if raw is not None and raw.lstrip("-").isdigit():
        return int(raw)
    return settings.delete_expired_after_hours


def _build_admin_panel_view() -> tuple[str, InlineKeyboardMarkup]:
    stats = db.get_stats()
    paused = bool(stats.get("is_paused"))
    by_topic = stats.get("pending_by_topic") or {}
    del_hours = _get_delete_expired_hours()
    if del_hours < 0:
        del_label = "Desativada (mantém tachado)"
    elif del_hours == 0:
        del_label = "Imediata (0h após encerrar)"
    else:
        del_label = f"Após {del_hours}h de encerrada"

    lines = [
        "🎛️ <b>PAINEL DE CONTROLE DO ADMINISTRADOR</b>",
        "",
        f"▶️ <b>Publicador:</b> {'⏸️ PAUSADO' if paused else '🟢 ATIVO (Round-Robin)'}",
        f"🌙 <b>Modo Noturno:</b> {'🔕 Ativo agora' if is_quiet_hours() else '🔔 Diurno normal'}",
        f"🧹 <b>Auto-Limpeza Encerradas:</b> {del_label}",
        f"🌐 <b>Vitrine Web / Mini-App:</b> <code>http://127.0.0.1:{settings.web_port}</code>",
        f"📥 <b>Fila Pendente:</b> <b>{stats['pending_queue']}</b> ofertas",
        f"📤 <b>Total Publicado:</b> <b>{stats['posted_total']}</b> ofertas",
        "",
        "📂 <b>Fila por Tópico:</b>",
    ]
    for t_key, t_name in OFFICIAL_TOPICS.items():
        lines.append(f"• {t_name}: <b>{by_topic.get(t_key, 0)}</b> na fila")

    toggle_btn = (
        InlineKeyboardButton("▶️ Retomar Publicação", callback_data="panel:resume")
        if paused
        else InlineKeyboardButton("⏸️ Pausar Publicação", callback_data="panel:pause")
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                toggle_btn,
                InlineKeyboardButton("🔍 Forçar Busca", callback_data="panel:scan"),
            ],
            [
                InlineKeyboardButton("📋 Gerenciar Fila", callback_data="panel:queue"),
                InlineKeyboardButton("📊 Relatório 24h", callback_data="panel:report"),
            ],
            [
                InlineKeyboardButton("🏆 Postar Top 5", callback_data="panel:top5"),
                InlineKeyboardButton("🧹 Limpar Fila", callback_data="panel:clear"),
            ],
            [
                InlineKeyboardButton("🔄 Atualizar Painel", callback_data="panel:refresh"),
                InlineKeyboardButton("🗑️ Auto-Limpeza Exp.", callback_data="panel:toggle_del_exp"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def cmd_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    stats = db.get_stats()
    topics = db.get_all_topics()
    by_topic = stats.get("pending_by_topic", {})

    lines = [
        "🤖 <b>Status do Bot de Promoções em Tópicos</b>",
        "",
        f"🆔 <b>Grupo Configurado (chat_id):</b> <code>{stats['chat_id'] or 'Não configurado'}</code>",
        f"▶️ <b>Estado do Publicador:</b> {'⏸️ PAUSADO (/retomar)' if stats.get('is_paused') else '🟢 ATIVO (Round-Robin)'}",
        f"🌙 <b>Modo Noturno Silencioso ({settings.quiet_hours_start}–{settings.quiet_hours_end}):</b> {'🔕 Ativo agora' if is_quiet_hours() else '🔔 Horário diurno normal'}",
        f"🔒 <b>Bloqueio Não-Admins:</b> ✅ Ativo em todos os tópicos",
        f"📥 <b>Ofertas Aguardando na Fila:</b> <b>{stats['pending_queue']}</b>",
        f"📤 <b>Ofertas Já Publicadas:</b> <b>{stats['posted_total']}</b>",
        f"🔗 <b>Afiliado ML (Fallback matt_tool):</b> {'✅ Ativo' if settings.has_ml_fallback else '⚠️ Pendente no .env'}",
        f"🍪 <b>Afiliado ML (Cookie /sec/):</b> {'✅ Configurado' if settings.has_ml_cookie else 'ℹ️ Usando Fallback URL'}",
        "",
        f"📂 <b>Tópicos ({stats['configured_topics']}/{stats['total_topics']}):</b>",
    ]
    for t in topics:
        tid = t["thread_id"]
        tkey = t["topic_key"]
        queued_n = by_topic.get(tkey, 0)
        badge = f"✅ <code>#{tid}</code> ({queued_n} na fila)" if tid else "❌ <i>Pendente (/configurar)</i>"
        lines.append(f"• {t['topic_name']} — {badge}")

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_fila(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    pending_items = db.list_pending_queue(limit=10)
    stats = db.get_stats()
    if not pending_items:
        await message.reply_text(
            "📭 <b>A fila de ofertas está vazia no momento.</b>\n"
            "Use <code>/forcar_busca</code> se quiser buscar novas promoções agora.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [
        f"📋 <b>Próximas Ofertas na Fila ({len(pending_items)} de {stats['pending_queue']} pendentes):</b>",
        "",
    ]
    for idx, item in enumerate(pending_items, start=1):
        t_name = OFFICIAL_TOPICS.get(item["topic_key"], item["topic_key"])
        disc_str = f" (-{item['discount_pct']}%)" if item.get("discount_pct") else ""
        title_safe = html.escape(str(item["title"])[:65])
        lines.append(
            f"<b>{idx}.</b> [{t_name}] <b>R$ { float(item['price']):.2f}</b>{disc_str} — "
            f"{title_safe} <i>({html.escape(str(item['store']))})</i>"
        )

    lines.append("")
    lines.append("💡 <i>Use <code>/limpar_fila</code> para esvaziar a fila ou <code>/pausar</code> / <code>/retomar</code>.</i>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_limpar_fila(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    topic_filter = context.args[0].strip().lower() if context.args else None
    removed = db.clear_pending_queue(topic_key=topic_filter)
    if topic_filter:
        await message.reply_text(
            f"🧹 <b>Fila limpa para o tópico <code>{html.escape(topic_filter)}</code>:</b> "
            f"<b>{removed}</b> oferta(s) descartada(s).",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            f"🧹 <b>Fila de ofertas limpa com sucesso!</b> "
            f"<b>{removed}</b> oferta(s) pendente(s) descartada(s).",
            parse_mode=ParseMode.HTML,
        )


async def cmd_pausar(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    db.set_paused(True)
    await message.reply_text(
        "⏸️ <b>Publicação automática PAUSADA!</b>\n"
        "Os coletores continuarão alimentando a fila em segundo plano. "
        "Envie <code>/retomar</code> quando quiser voltar a publicar.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_retomar(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    db.set_paused(False)
    await message.reply_text(
        "▶️ <b>Publicação automática RETOMADA!</b>\n"
        "O Bot voltará a postar as ofertas da fila em rodízio entre os tópicos.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_testar_oferta(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    if not db.get_chat_id() and chat.type == "supergroup":
        db.set_chat_id(chat.id)

    sample_raw_url = (
        "https://produto.mercadolivre.com.br/MLB-39481029-chocolate-milka-oreo-300g-_JM"
        "?matt_tool=99999999&matt_word=pelando&tracking_id=abc#polycard"
    )
    affiliate_url = await convert_to_affiliate_url(sample_raw_url)

    demo_offer = {
        "offer_key": "ml:MLB39481029",
        "title": "Barra de Chocolate Importado Milka Mmmax Oreo 300g",
        "price": 24.90,
        "original_price": 44.90,
        "discount_pct": 44,
        "coupon": "DOCE10",
        "store": "Mercado Livre",
        "is_full": True,
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_608688-MLU72637408212_112023-F.jpg",
        "affiliate_url": affiliate_url,
        "original_url": sample_raw_url,
        "topic_key": "doces_importados",
    }

    ok = await publish_offer(context.bot, demo_offer, database=db)
    if ok:
        await message.reply_text(
            "✅ <b>Oferta de teste publicada com sucesso no tópico de Doces Importados!</b>\n"
            f"🔗 <b>Link gerado:</b> <code>{affiliate_url}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "❌ Falha ao publicar oferta de teste. Verifique se o grupo possui Tópicos ativados e rode <code>/configurar</code>.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_postar(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    if not context.args:
        await message.reply_text(
            "ℹ️ <b>Uso do comando (exclusivo Admins):</b>\n"
            "<code>/postar https://produto.mercadolivre.com.br/MLB-... [CUPOM]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_url = context.args[0].strip()
    coupon = " ".join(context.args[1:]).strip() if len(context.args) > 1 else None

    status_msg = await message.reply_text(
        "⏳ <b>Extraindo dados do produto e gerando link de afiliado...</b>",
        parse_mode=ParseMode.HTML,
    )

    scraped = await scrape_single_product_url(raw_url, coupon=coupon)
    if not scraped:
        await status_msg.edit_text(
            "❌ <b>Não foi possível extrair título/preço automaticamente deste link.</b>\n"
            "Verifique se o link é válido e aponta para a página de um produto.",
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

    offer_payload = {
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

    ok = await publish_offer(context.bot, offer_payload, database=db)
    if ok:
        db.record_posted_offer(
            offer_key=offer_key,
            title=scraped.title,
            price=scraped.price,
            topic_key=topic_key,
            original_price=scraped.original_price,
            affiliate_url=affiliate_url,
            original_url=scraped.url,
            message_id=offer_payload.get("_sent_message_id"),
            thread_id=offer_payload.get("_sent_thread_id"),
            has_photo=bool(offer_payload.get("_sent_has_photo")),
            caption_html=offer_payload.get("_sent_caption_html"),
        )
        topic_label = OFFICIAL_TOPICS.get(topic_key, topic_key)
        await status_msg.edit_text(
            f"✅ <b>Oferta publicada imediatamente em [{topic_label}]!</b>\n"
            f"📦 <b>Produto:</b> {html.escape(scraped.title[:70])}\n"
            f"💰 <b>Preço:</b> R$ {scraped.price:.2f}\n"
            f"🔗 <b>Link Afiliado:</b> <code>{html.escape(affiliate_url)}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await status_msg.edit_text(
            "❌ Falha ao publicar a oferta no grupo. Verifique o <code>/status</code>.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_resumo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    ok = await publish_daily_top5_summary(context.bot, database=db)
    if ok:
        await message.reply_text(
            "🏆 <b>Resumo Top 5 Melhores Promoções do Dia publicado no tópico de Destaques/Bugs!</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "ℹ️ Ainda não há ofertas enviadas suficientes nas últimas 24h ou o Bot está pausado.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_relatorio(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    report = db.get_24h_operational_report()
    report_html = format_operational_report(report)
    await message.reply_text(report_html, parse_mode=ParseMode.HTML)


async def cmd_cookie(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    if not context.args:
        has_cookie = bool(db.get_config("ml_affiliate_cookie") or settings.has_ml_cookie)
        await message.reply_text(
            "🍪 <b>Atualização Dinâmica de Cookie do Mercado Livre</b>\n\n"
            f"• <b>Status atual:</b> {'✅ Configurado' if has_cookie else '⚠️ Não configurado (usando Fallback matt_tool)'}\n\n"
            "Para atualizar o cookie sem reiniciar o bot, envie no chat privado:\n"
            "<code>/cookie SEU_COOKIE_COMPLETO_DO_LINKBUILDER</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    new_cookie = " ".join(context.args).strip()
    db.set_config("ml_affiliate_cookie", new_cookie)
    db.set_config("ml_cookie_expired_pending", "0")
    await message.reply_text(
        "✅ <b>Cookie do Mercado Livre atualizado com sucesso no banco de dados!</b>\n"
        "Os próximos links do Mercado Livre já tentarão gerar links curtos oficiais <code>/sec/</code>.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_afiliado(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    if not context.args or len(context.args) < 2:
        lines = [
            "💰 <b>Configuração de Afiliados Multilojas</b>",
            "",
        ]
        for k, label in _AFFILIATE_CONFIG_KEYS.items():
            val = db.get_config(k) or getattr(settings, k, "") or ""
            is_valid = bool(
                val
                and val not in ("SEU_MATT_TOOL", "SEU_MATT_WORD", "SUA_TAG_DE_AFILIADO", "SUA_TAG_AMAZON", "SEU_ID_SHOPEE", "SUA_LOJA_MAGALU")
            )
            status = f"✅ <code>{html.escape(val)}</code>" if is_valid else "⚠️ <i>Não configurado</i>"
            lines.append(f"• <b>{label}</b> (<code>{k}</code>): {status}")

        lines.extend(
            [
                "",
                "💡 <b>Como configurar pelo Telegram:</b>",
                "<code>/afiliado ml_matt_tool 12345678</code>",
                "<code>/afiliado ml_matt_word meucanal</code>",
                "<code>/afiliado amazon_affiliate_tag meucanal-20</code>",
                "<code>/afiliado shopee_affiliate_id 1122334455</code>",
                "<code>/afiliado magalu_store_slug minhalojamagalu</code>",
            ]
        )
        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    key = context.args[0].strip().lower()
    value = " ".join(context.args[1:]).strip()
    if key not in _AFFILIATE_CONFIG_KEYS:
        await message.reply_text(
            f"❌ Chave inválida. Chaves aceitas: <code>{', '.join(_AFFILIATE_CONFIG_KEYS.keys())}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    db.set_config(key, value)
    await message.reply_text(
        f"✅ <b>{_AFFILIATE_CONFIG_KEYS[key]}</b> atualizado para: <code>{html.escape(value)}</code>!\n"
        "Todas as próximas conversões já usarão essa credencial automaticamente.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_painel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    text, kb = _build_admin_panel_view()
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cmd_forcar_busca(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "🔍 <b>Iniciando varredura imediata nas 3 frentes (Agregadores, Ofertas ML e Caçador de Importados)...</b>",
        parse_mode=ParseMode.HTML,
    )

    c1, c2, c3 = await asyncio.gather(
        job_scrape_ml_imported_hunter(),
        job_scrape_ml_offers(),
        job_scrape_aggregators(),
    )
    total = c1 + c2 + c3
    await message.reply_text(
        f"✅ <b>Varredura concluída!</b>\n"
        f"• Caçador de Importados: <b>{c1}</b> novas ofertas\n"
        f"• Ofertas Oficiais ML: <b>{c2}</b> novas ofertas\n"
        f"• Agregadores: <b>{c3}</b> novas ofertas\n\n"
        f"📥 <b>Total adicionado na fila:</b> <b>{total}</b>",
        parse_mode=ParseMode.HTML,
    )
