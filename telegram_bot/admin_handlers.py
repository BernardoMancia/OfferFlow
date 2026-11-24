from __future__ import annotations

import asyncio
import html
from typing import Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from affiliate.mercadolivre import (
    convert_to_affiliate_url,
    has_active_ml_affiliate,
    is_monetized_ml_url,
)
from affiliate.url_cleaner import extract_offer_key, is_mercadolivre_url
from classifier.catalogs import BOT_BRAND_NAME, CHANNEL_CATALOG, OFFICIAL_TOPICS
from classifier.ml_compliance import evaluate_ml_compliance
from classifier.topic_router import classify_offer_topic
from config import settings
from core.scheduler import (
    job_scrape_aggregators,
    job_scrape_ml_categories,
    job_scrape_ml_offers,
)
from database.db import db
from scrapers.ml_offers import scrape_single_product_url
from telegram_bot.channel_manager import (
    bind_and_style_channel,
    build_channels_status_text,
    build_setup_guide_text,
    execute_affiliate_link_autoconfig,
    refresh_hub_directory,
)
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
}


async def is_global_admin(bot, user_id: int) -> bool:
    if user_id in db.get_admin_user_ids():
        return True

    check_chat_ids = []
    hub = db.get_hub_channel()
    if hub and hub.get("chat_id"):
        check_chat_ids.append(int(hub["chat_id"]))
    group_id = db.get_chat_id()
    if group_id:
        check_chat_ids.append(int(group_id))
    for ch in db.get_all_channels(include_hub=False):
        if ch.get("chat_id"):
            check_chat_ids.append(int(ch["chat_id"]))
            break

    for cid in check_chat_ids:
        if await is_user_admin(bot, cid, user_id):
            db.add_admin_user_id(user_id)
            return True
    return False


async def _check_command_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if not chat or not message:
        return False

    if (
        chat.type == ChatType.SUPERGROUP
        and message.sender_chat
        and message.sender_chat.id == chat.id
    ):
        return True

    if user and await is_global_admin(context.bot, user.id):
        if chat.type == ChatType.PRIVATE:
            db.set_config("admin_private_chat_id", str(chat.id))
        return True

    if chat.type == ChatType.SUPERGROUP:
        if user and await is_user_admin(context.bot, chat.id, user.id):
            db.add_admin_user_id(user.id)
            return True
        try:
            await message.delete()
        except TelegramError:
            pass
        await lock_group_for_non_admins(context.bot, chat.id)
    else:
        has_any_owner = bool(
            db.get_admin_user_ids()
            or db.get_linked_category_keys()
            or (db.get_hub_channel() or {}).get("chat_id")
        )
        if not has_any_owner and db.get_chat_id():
            try:
                await context.bot.get_chat(int(db.get_chat_id()))
                has_any_owner = True
            except TelegramError:
                has_any_owner = False
        try:
            if not has_any_owner and user:
                await message.reply_text(
                    "⚙️ <b>Primeiro Acesso Detectado:</b>\n"
                    f"Adicione <code>ADMIN_USER_IDS={user.id}</code> no seu arquivo <code>.env</code> e reinicie o Bot "
                    "para liberar os comandos de Administrador.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await message.reply_text(
                    "⛔ <b>Acesso Negado:</b> Apenas Administradores da Comunidade OfferFlow podem usar este comando.",
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
    aff_active = has_active_ml_affiliate()
    del_hours = _get_delete_expired_hours()
    if del_hours < 0:
        del_label = "Desativada (mantém tachado)"
    elif del_hours == 0:
        del_label = "Imediata (0h após encerrar)"
    else:
        del_label = f"Após {del_hours}h de encerrada"

    lines = [
        f"🎛️ <b>PAINEL DE CONTROLE DO ADMINISTRADOR • {BOT_BRAND_NAME.upper()}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"▶️ <b>Publicador:</b> {'⏸️ PAUSADO' if paused else '🟢 ATIVO (100% ML • Round-Robin)'}",
        f"💰 <b>Afiliado ML:</b> {'✅ Monetização 100% Ativa' if aff_active else '🔴 PENDENTE (/configurar_afiliado)'}",
        f"📢 <b>Canais Vinculados:</b> <b>{stats.get('linked_channels', 0)}/{stats.get('total_channels', 8)}</b> | Comunidade Hub: {'✅' if stats.get('hub_linked') else '⚠️'}",
        f"🌙 <b>Modo Noturno:</b> {'🔕 Ativo agora' if is_quiet_hours() else '🔔 Diurno normal'}",
        f"🧹 <b>Auto-Limpeza Encerradas:</b> {del_label}",
        f"📥 <b>Fila Pendente:</b> <b>{stats['pending_queue']}</b> | 📤 <b>Publicado:</b> <b>{stats['posted_total']}</b>",
        "",
        "📂 <b>Fila por Canal (8 Categorias Comissionadas ML):</b>",
    ]
    for t_key, t_name in OFFICIAL_TOPICS.items():
        ch_ok = "✅" if db.get_channel_chat_id(t_key) else "⬜"
        lines.append(f"{ch_ok} {t_name}: <b>{by_topic.get(t_key, 0)}</b> na fila")

    toggle_btn = (
        InlineKeyboardButton("▶️ Retomar", callback_data="panel:resume")
        if paused
        else InlineKeyboardButton("⏸️ Pausar", callback_data="panel:pause")
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                toggle_btn,
                InlineKeyboardButton("🔍 Forçar Busca ML", callback_data="panel:scan"),
            ],
            [
                InlineKeyboardButton("📢 Mapa Canais", callback_data="panel:channels"),
                InlineKeyboardButton("📊 Relatório 24h", callback_data="panel:report"),
            ],
            [
                InlineKeyboardButton("📋 Gerenciar Fila", callback_data="panel:queue"),
                InlineKeyboardButton("🏆 Postar Top 5", callback_data="panel:top5"),
            ],
            [
                InlineKeyboardButton("🔄 Atualizar", callback_data="panel:refresh"),
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
    aff_ok = has_active_ml_affiliate()
    by_topic = stats.get("pending_by_topic", {})

    lines = [
        f"🤖 <b>Status do {BOT_BRAND_NAME} (100% Mercado Livre Afiliados)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"▶️ <b>Publicador:</b> {'⏸️ PAUSADO (/retomar)' if stats.get('is_paused') else '🟢 ATIVO (Round-Robin)'}",
        f"💰 <b>Monetização ML:</b> {'✅ ATIVA (Trava de Afiliado Ligada)' if aff_ok else '🔴 PENDENTE — envie /configurar_afiliado <seu_link_ml>'}",
        f"📢 <b>Canais de Categoria:</b> <b>{stats.get('linked_channels', 0)}/{stats.get('total_channels', 8)}</b> | Hub: {'✅ Vinculado' if stats.get('hub_linked') else '⚠️ Pendente'}",
        f"🌙 <b>Modo Noturno ({settings.quiet_hours_start}–{settings.quiet_hours_end}):</b> {'🔕 Ativo agora' if is_quiet_hours() else '🔔 Horário diurno'}",
        f"📥 <b>Na Fila:</b> <b>{stats['pending_queue']}</b> | 📤 <b>Publicadas:</b> <b>{stats['posted_total']}</b>",
        "",
        "📂 <b>Canais Comissionados ML:</b>",
    ]
    for ch in db.get_all_channels(include_hub=False):
        ckey = ch["category_key"]
        queued_n = by_topic.get(ckey, 0)
        badge = f"✅ vinculado ({queued_n} na fila)" if ch.get("chat_id") else f"⬜ use <code>/vincular {ckey}</code>"
        lines.append(f"• {OFFICIAL_TOPICS.get(ckey, ckey)} — {badge}")

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_canais(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        build_channels_status_text(db),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_guia_configuracao(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        build_setup_guide_text(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_pasta(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    if not context.args:
        current = db.get_folder_url()
        await message.reply_text(
            "📂 <b>Link da Pasta de Canais da Comunidade OfferFlow</b>\n\n"
            f"• <b>Atual:</b> {html.escape(current) if current else '<i>Não configurado</i>'}\n\n"
            "Para definir ou atualizar, envie:\n"
            "<code>/pasta https://t.me/addlist/SEU_CODIGO</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    folder_url = context.args[0].strip()
    if not folder_url.startswith("http"):
        await message.reply_text(
            "⚠️ Informe uma URL válida começando com <code>https://t.me/addlist/...</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    db.set_folder_url(folder_url)
    refreshed = await refresh_hub_directory(context.bot, database=db)
    await message.reply_text(
        "✅ <b>Link da Pasta salvo com sucesso!</b>\n"
        + ("📢 Diretório fixado da Comunidade Hub atualizado!" if refreshed else "ℹ️ Assim que vincular o canal <code>hub</code>, o botão aparecerá fixado no topo."),
        parse_mode=ParseMode.HTML,
    )


async def cmd_configurar_afiliado(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    if not context.args:
        await message.reply_text(
            "💰 <b>Configuração Automática do Afiliado Mercado Livre</b>\n\n"
            "Gere qualquer link na sua Barra de Afiliados do Mercado Livre (pode ser <code>https://mercadolivre.com/sec/...</code> ou o link longo com <code>matt_tool</code>) e envie:\n\n"
            "<code>/configurar_afiliado COLE_SEU_LINK_AQUI</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_url = context.args[0].strip()
    status_msg = await message.reply_text(
        "⏳ <b>Analisando seu link de afiliado do Mercado Livre...</b>",
        parse_mode=ParseMode.HTML,
    )
    _, reply_html = await execute_affiliate_link_autoconfig(raw_url, database=db)
    await status_msg.edit_text(reply_html, parse_mode=ParseMode.HTML)


async def cmd_vincular(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    if not context.args:
        keys = "\n".join(f"• <code>{k}</code> — {v['short_name']}" for k, v in CHANNEL_CATALOG.items())
        await message.reply_text(
            "📢 <b>Como vincular um Canal:</b>\n"
            "Adicione o Bot como Administrador no canal e poste lá dentro:\n"
            "<code>/vincular CHAVE_DA_CATEGORIA</code>\n\n"
            f"<b>Chaves válidas:</b>\n{keys}",
            parse_mode=ParseMode.HTML,
        )
        return

    cat_key = context.args[0].strip().lower()
    target_chat_id = chat.id
    if len(context.args) >= 2:
        raw_cid = context.args[1].strip()
        if raw_cid.lstrip("-").isdigit():
            target_chat_id = int(raw_cid)

    ok, result_msg = await bind_and_style_channel(
        context.bot, target_chat_id, cat_key, database=db
    )
    prefix = "✅" if ok else "❌"
    await message.reply_text(
        f"{prefix} <b>{html.escape(result_msg)}</b>",
        parse_mode=ParseMode.HTML,
    )


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
            f"<b>{idx}.</b> [{t_name}] <b>R$ {float(item['price']):.2f}</b>{disc_str} — {title_safe}"
        )

    lines.append("")
    lines.append("💡 <i>Use <code>/limpar_fila</code> para esvaziar ou <code>/pausar</code> / <code>/retomar</code>.</i>")
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
            f"🧹 <b>Fila limpa para <code>{html.escape(topic_filter)}</code>:</b> <b>{removed}</b> oferta(s) descartada(s).",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            f"🧹 <b>Fila limpa com sucesso!</b> <b>{removed}</b> oferta(s) pendente(s) descartada(s).",
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
        "Envie <code>/retomar</code> quando quiser voltar a publicar nos canais.",
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
        "O OfferFlow voltará a distribuir ofertas em rodízio pelos canais vinculados.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_testar_oferta(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_command_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    if not has_active_ml_affiliate():
        await message.reply_text(
            "⚠️ <b>Configure primeiro seu link de afiliado Mercado Livre!</b>\n"
            "Envie: <code>/configurar_afiliado COLE_SEU_LINK_DE_AFILIADO_ML</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    sample_raw_url = (
        "https://produto.mercadolivre.com.br/MLB-39481029-monitor-gamer-lg-ultragear-27-_JM"
    )
    affiliate_url = await convert_to_affiliate_url(sample_raw_url)
    if not affiliate_url or not is_monetized_ml_url(affiliate_url):
        await message.reply_text(
            "❌ Falha ao gerar link monetizado. Verifique <code>/afiliado</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    demo_offer = {
        "offer_key": "ml:MLB39481029",
        "title": "Monitor Gamer LG UltraGear 27 IPS 180Hz 1ms Full HD",
        "price": 899.00,
        "original_price": 1399.00,
        "discount_pct": 36,
        "coupon": "MELI10",
        "installments": "em 10x de R$ 89,90 sem juros",
        "store": "Mercado Livre",
        "is_full": True,
        "rating": 4.9,
        "reviews_count": 1420,
        "condition": "new",
        "seller_reputation": "green",
        "image_url": "https://http2.mlstatic.com/D_NQ_NP_2X_608688-MLU72637408212_112023-F.jpg",
        "affiliate_url": affiliate_url,
        "original_url": sample_raw_url,
        "topic_key": "tech_celulares",
    }

    ok = await publish_offer(context.bot, demo_offer, database=db)
    if ok:
        await message.reply_text(
            "✅ <b>Oferta de teste publicada com sucesso no padrão Editorial Premium!</b>\n"
            f"🔗 <b>Link gerado:</b> <code>{html.escape(affiliate_url)}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "❌ Nenhum canal vinculado para <code>tech_celulares</code>. Use <code>/guia_configuracao</code>.",
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
            "ℹ️ <b>Uso (100% Mercado Livre):</b>\n"
            "<code>/postar https://produto.mercadolivre.com.br/MLB-... [CUPOM]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_url = context.args[0].strip()
    coupon = " ".join(context.args[1:]).strip() if len(context.args) > 1 else None

    status_msg = await message.reply_text(
        "⏳ <b>Validando compliance ML, extraindo produto e gerando seu link de afiliado...</b>",
        parse_mode=ParseMode.HTML,
    )

    scraped = await scrape_single_product_url(raw_url, coupon=coupon)
    if not scraped or not is_mercadolivre_url(scraped.url):
        await status_msg.edit_text(
            "❌ <b>Apenas produtos do Mercado Livre são aceitos.</b>\n"
            "Verifique se o link aponta para um anúncio válido do Mercado Livre.",
            parse_mode=ParseMode.HTML,
        )
        return

    comp = evaluate_ml_compliance(
        title=scraped.title,
        url=scraped.url,
        condition=scraped.condition,
        seller_reputation=scraped.seller_reputation,
    )
    if not comp.approved:
        await status_msg.edit_text(
            f"⛔ <b>Bloqueado pelo padrão oficial de Afiliados ML:</b>\n{html.escape(comp.reason)}",
            parse_mode=ParseMode.HTML,
        )
        return

    affiliate_url = await convert_to_affiliate_url(scraped.url)
    if not affiliate_url:
        await status_msg.edit_text(
            "⚠️ <b>Monetização ML pendente!</b> Configure seu link de afiliado primeiro com:\n"
            "<code>/configurar_afiliado COLE_SEU_LINK_DE_AFILIADO_ML</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    topic_key = (
        classify_offer_topic(
            title=scraped.title,
            discount_pct=scraped.discount_pct,
            coupon=scraped.coupon,
            price=scraped.price,
            url=scraped.url,
            condition=comp.normalized_condition,
            seller_reputation=comp.normalized_reputation,
        )
        or "ofertas_bugs"
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
        "store": "Mercado Livre",
        "is_full": scraped.is_full,
        "image_url": scraped.image_url,
        "affiliate_url": affiliate_url,
        "original_url": scraped.url,
        "topic_key": topic_key,
        "rating": scraped.rating,
        "reviews_count": scraped.reviews_count,
        "condition": comp.normalized_condition,
        "seller_reputation": comp.normalized_reputation,
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
            target_chat_id=offer_payload.get("_sent_chat_id"),
        )
        topic_label = OFFICIAL_TOPICS.get(topic_key, topic_key)
        await status_msg.edit_text(
            f"✅ <b>Oferta publicada em [{topic_label}]!</b>\n"
            f"📦 <b>Produto:</b> {html.escape(scraped.title[:70])}\n"
            f"💰 <b>Preço:</b> R$ {scraped.price:.2f}\n"
            f"🔗 <b>Link Afiliado:</b> <code>{html.escape(affiliate_url)}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await status_msg.edit_text(
            "❌ Falha ao publicar. Verifique se o canal da categoria está vinculado em <code>/canais</code>.",
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
            "🏆 <b>Resumo Top 5 Melhores Ofertas do Dia publicado na Comunidade OfferFlow!</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "ℹ️ Sem ofertas enviadas nas últimas 24h ou Comunidade Hub ainda não vinculada.",
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
    await message.reply_text(format_operational_report(report), parse_mode=ParseMode.HTML)


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
            "Para atualizar sem reiniciar:\n"
            "<code>/cookie SEU_COOKIE_COMPLETO_DO_LINKBUILDER</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    new_cookie = " ".join(context.args).strip()
    db.set_config("ml_affiliate_cookie", new_cookie)
    db.set_config("ml_cookie_expired_pending", "0")
    await message.reply_text(
        "✅ <b>Cookie do Mercado Livre atualizado com sucesso!</b>\n"
        "Os próximos links tentarão gerar links curtos oficiais <code>/sec/</code>.",
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
            "💰 <b>Configuração de Afiliado Mercado Livre (100% ML)</b>",
            "",
        ]
        for k, label in _AFFILIATE_CONFIG_KEYS.items():
            val = db.get_config(k) or getattr(settings, k, "") or ""
            is_valid = bool(
                val
                and val not in ("SEU_MATT_TOOL", "SEU_MATT_WORD", "SUA_TAG_DE_AFILIADO")
            )
            status = f"✅ <code>{html.escape(val)}</code>" if is_valid else "⚠️ <i>Não configurado</i>"
            lines.append(f"• <b>{label}</b> (<code>{k}</code>): {status}")

        lines.extend(
            [
                "",
                "⚡ <b>Jeito mais fácil (automático):</b>",
                "<code>/configurar_afiliado COLE_QUALQUER_LINK_DE_AFILIADO_SEU_DO_ML</code>",
                "",
                "🛠️ <b>Ou manual:</b>",
                "<code>/afiliado ml_matt_tool 12345678</code>",
                "<code>/afiliado ml_matt_word meucanal</code>",
                "<code>/afiliado ml_affiliate_tag sua_tag</code>",
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
        f"✅ <b>{_AFFILIATE_CONFIG_KEYS[key]}</b> atualizado para: <code>{html.escape(value)}</code>!",
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
        "🔍 <b>Iniciando varredura 100% Mercado Livre nas 3 frentes (Ofertas ML, Mais Vendidos e Agregadores ML-Only)...</b>",
        parse_mode=ParseMode.HTML,
    )

    c1, c2, c3 = await asyncio.gather(
        job_scrape_ml_offers(),
        job_scrape_ml_categories(),
        job_scrape_aggregators(),
    )
    total = c1 + c2 + c3
    await message.reply_text(
        f"✅ <b>Varredura 100% Mercado Livre concluída!</b>\n"
        f"• Frente A (Ofertas Oficiais & Relâmpago ML): <b>{c1}</b> novas\n"
        f"• Frente B (Mais Vendidos por Categoria ML): <b>{c2}</b> novas\n"
        f"• Frente C (Agregadores filtrados ML-Only): <b>{c3}</b> novas\n\n"
        f"📥 <b>Total adicionado na fila:</b> <b>{total}</b>",
        parse_mode=ParseMode.HTML,
    )
