from __future__ import annotations

import html
import time
from datetime import datetime
from typing import Any, Dict, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from affiliate.mercadolivre import consume_ml_cookie_expired_alert
from config import OFFICIAL_TOPICS, settings
from database.db import DatabaseManager, db
from database.logger import get_logger
from telegram_bot.formatter import (
    build_offer_keyboard,
    format_brl,
    format_daily_top5_summary,
    format_offer_message,
    format_operational_report,
)
from telegram_bot.setup_topics import (
    ensure_forum_topics,
    recreate_single_topic,
    sync_group_metadata,
)

logger = get_logger("telegram.publisher")


def _parse_hhmm(value: str, default_h: int, default_m: int) -> int:

    try:
        parts = value.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return default_h * 60 + default_m


def is_quiet_hours(now: Optional[datetime] = None) -> bool:
\
\
\

    dt = now or datetime.now()
    current_min = dt.hour * 60 + dt.minute
    start_min = _parse_hhmm(settings.quiet_hours_start, 23, 30)
    end_min = _parse_hhmm(settings.quiet_hours_end, 7, 30)

    if start_min <= end_min:
        return start_min <= current_min < end_min

    return current_min >= start_min or current_min < end_min


async def _notify_if_ml_cookie_expired(bot: Bot, chat_id: int, database: DatabaseManager) -> None:

    if not consume_ml_cookie_expired_alert():
        return

    now_ts = int(time.time())
    last_ts_raw = database.get_config("last_ml_cookie_alert_ts", "0") or "0"
    try:
        last_ts = int(last_ts_raw)
    except ValueError:
        last_ts = 0

    if now_ts - last_ts < 86400:
        return

    database.set_config("last_ml_cookie_alert_ts", str(now_ts))
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ <b>Aviso de Manutenção (Afiliado ML):</b>\n"
                "O seu <code>ML_SESSION_COOKIE</code> parece ter expirado ou retornado sessão inválida ao gerar link curto <code>/sec/</code>.\n\n"
                "✅ <b>Fique tranquilo:</b> O Bot ativou automaticamente o <b>Fallback Oficial</b> "
                "(<code>matt_tool</code> / <code>matt_word</code>) e todas as postagens continuam monetizadas!\n"
                "💡 <i>Quando puder, atualize o cookie no arquivo <code>.env</code> para voltar a usar links curtos <code>meli.la</code> / <code>/sec/</code>.</i>"
            ),
            parse_mode=ParseMode.HTML,
            disable_notification=True,
        )
    except TelegramError as exc:
        logger.warning(f"Não foi possível enviar alerta de cookie ML expirado: {exc}")


async def publish_offer(
    bot: Bot,
    offer: Dict[str, Any],
    database: DatabaseManager = db,
) -> bool:
\
\
\

    chat_id = database.get_chat_id()
    if not chat_id:
        logger.warning(
            "Nenhum chat_id configurado ainda. Adicione o Bot como Admin no Supergrupo com Tópicos."
        )
        return False

    await _notify_if_ml_cookie_expired(bot, chat_id, database)

    topic_key = str(offer.get("topic_key") or "bugs_imperdiveis")
    thread_id = database.get_topic_thread_id(topic_key)

    if thread_id is None:
        await ensure_forum_topics(bot, chat_id, database=database)
        thread_id = database.get_topic_thread_id(topic_key)

    offer_payload = dict(offer)
    offer_key = offer_payload.get("offer_key")
    price_val = offer_payload.get("price")
    if offer_key and price_val is not None:
        hist_ctx = database.get_price_history_context(
            str(offer_key),
            float(price_val),
            title=str(offer_payload.get("title") or ""),
        )
        if "is_historical_low" not in offer_payload:
            offer_payload["is_historical_low"] = hist_ctx["is_historical_low"]
        if "savings_vs_low" not in offer_payload:
            offer_payload["savings_vs_low"] = hist_ctx["savings_vs_low"]

    caption = format_offer_message(offer_payload)
    keyboard = build_offer_keyboard(offer_payload)
    image_url = (offer_payload.get("image_url") or "").strip()

    discount_pct = int(offer_payload.get("discount_pct") or 0)
    silent_mode = is_quiet_hours() and discount_pct < 60

    async def _send(target_thread_id: int | None, use_photo: bool) -> bool:
        kwargs: Dict[str, Any] = {
            "chat_id": chat_id,
            "parse_mode": ParseMode.HTML,
            "reply_markup": keyboard,
            "disable_notification": silent_mode,
        }
        if target_thread_id is not None:
            kwargs["message_thread_id"] = target_thread_id

        if use_photo and image_url.startswith("http"):
            sent_msg = await bot.send_photo(
                photo=image_url,
                caption=caption,
                **kwargs,
            )
            used_photo = True
        else:
            sent_msg = await bot.send_message(
                text=caption,
                disable_web_page_preview=False,
                **kwargs,
            )
            used_photo = False

        if sent_msg and isinstance(offer, dict):
            offer["_sent_message_id"] = sent_msg.message_id
            offer["_sent_thread_id"] = target_thread_id
            offer["_sent_has_photo"] = used_photo
            offer["_sent_caption_html"] = caption


        if discount_pct >= 60 and topic_key == "bugs_imperdiveis" and sent_msg:
            try:
                await bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=sent_msg.message_id,
                    disable_notification=True,
                )
                logger.info(
                    f"Super Bug ({discount_pct}% OFF) fixado automaticamente no tópico [{topic_key}] (msg_id={sent_msg.message_id})."
                )
            except TelegramError as pin_exc:
                logger.debug(f"Não foi possível fixar Super Bug: {pin_exc}")

        return True

    try:
        await _send(thread_id, use_photo=bool(image_url))
        logger.info(
            f"Oferta publicada em [{topic_key}] (thread={thread_id}, silent={silent_mode}): "
            f"{offer_payload.get('title')} - R$ {offer_payload.get('price')}"
        )
        await _notify_matched_user_alerts(
            bot,
            offer_payload=offer_payload,
            group_chat_id=chat_id,
            sent_message_id=offer.get("_sent_message_id") if isinstance(offer, dict) else None,
            sent_thread_id=thread_id,
            database=database,
        )
        return True

    except BadRequest as exc:
        err_msg = str(exc).lower()


        if "thread not found" in err_msg or "message_thread_id" in err_msg:
            logger.warning(
                f"Tópico [{topic_key}] (thread={thread_id}) não encontrado no Telegram. Recriando..."
            )
            new_thread_id = await recreate_single_topic(
                bot, chat_id, topic_key, database=database
            )
            if new_thread_id:
                try:
                    await _send(new_thread_id, use_photo=bool(image_url))
                    return True
                except TelegramError:
                    await _send(new_thread_id, use_photo=False)
                    return True


        if image_url:
            logger.warning(
                f"Falha ao enviar foto ({image_url}): {exc}. Enviando oferta apenas como mensagem HTML."
            )
            try:
                await _send(thread_id, use_photo=False)
                return True
            except TelegramError as retry_exc:
                logger.error(f"Erro ao enviar oferta como texto: {retry_exc}")
                return False

        logger.error(f"BadRequest ao publicar oferta: {exc}")
        return False

    except TelegramError as exc:
        logger.error(f"Erro da API do Telegram ao publicar oferta: {exc}")
        return False


async def _notify_matched_user_alerts(
    bot: Bot,
    offer_payload: Dict[str, Any],
    group_chat_id: int,
    sent_message_id: Optional[int],
    sent_thread_id: Optional[int],
    database: DatabaseManager = db,
) -> int:
\
\
\

    title = str(offer_payload.get("title") or "")
    price_num = float(offer_payload.get("price") or 0.0)
    matches = database.match_user_alerts(title, price=price_num if price_num > 0 else None)
    if not matches:
        return 0

    price_str = format_brl(float(offer_payload.get("price") or 0.0))
    aff_url = str(offer_payload.get("affiliate_url") or offer_payload.get("original_url") or "")
    topic_key = str(offer_payload.get("topic_key") or "bugs_imperdiveis")
    topic_label = OFFICIAL_TOPICS.get(topic_key, topic_key)


    group_post_url = None
    str_chat = str(group_chat_id)
    if str_chat.startswith("-100") and sent_message_id:
        clean_cid = str_chat[4:]
        if sent_thread_id:
            group_post_url = f"https://t.me/c/{clean_cid}/{sent_thread_id}/{sent_message_id}"
        else:
            group_post_url = f"https://t.me/c/{clean_cid}/{sent_message_id}"

    notified = 0
    for alert in matches:
        kw = html.escape(str(alert.get("keyword") or ""))
        target_chat_id = int(alert["chat_id"])
        text = (
            f"🔔 <b>ALERTA DE DESEJO ATINGIDO!</b> (<code>{kw}</code>)\n\n"
            f"📦 <b>{html.escape(title)}</b>\n"
            f"🔥 <b>Por:</b> <b>{price_str}</b>\n"
            f"📂 <b>Tópico:</b> {topic_label}\n"
        )
        buttons = [[InlineKeyboardButton("🛒 Pegar Promoção", url=aff_url)]]
        if group_post_url:
            buttons[0].append(InlineKeyboardButton("💬 Ver no Grupo", url=group_post_url))

        try:
            await bot.send_message(
                chat_id=target_chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            notified += 1
        except TelegramError as exc:
            logger.debug(f"Não foi possível notificar alerta para chat_id={target_chat_id}: {exc}")

    return notified


async def publish_daily_top5_summary(
    bot: Bot,
    database: DatabaseManager = db,
) -> bool:
\
\
\

    if database.is_paused():
        return False

    chat_id = database.get_chat_id()
    if not chat_id:
        return False

    top_offers = database.get_top_offers_last_24h(limit=5)
    if not top_offers:
        return False

    thread_id = database.get_topic_thread_id("bugs_imperdiveis")
    summary_html = format_daily_top5_summary(top_offers)

    kwargs: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": summary_html,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
    }
    if thread_id is not None:
        kwargs["message_thread_id"] = thread_id

    try:
        await bot.send_message(**kwargs)
        logger.info("Resumo Diário (Top 5 Promoções do Dia) publicado com sucesso!")
        return True
    except TelegramError as exc:
        logger.warning(f"Erro ao publicar Resumo Diário Top 5: {exc}")
        return False


async def process_next_queued_offer(
    bot: Bot,
    database: DatabaseManager = db,
    validate_live: bool = True,
) -> bool:
\
\
\

    if database.is_paused():
        logger.debug("Publicação pausada via /pausar. Aguardando /retomar.")
        return False

    chat_id = database.get_chat_id()
    if not chat_id:
        return False

    from scrapers.ml_offers import validate_live_offer_status

    for _attempt in range(3):
        item = database.get_next_pending_offer()
        if not item:
            return False

        queue_id = int(item["id"])
        check_url = str(item.get("original_url") or item.get("affiliate_url") or "")
        expected_price = float(item.get("price") or 0.0)
        has_coupon = bool(item.get("coupon"))

        if validate_live and check_url:
            is_valid, live_price, live_orig, reason = await validate_live_offer_status(
                check_url,
                expected_price=expected_price,
                has_coupon=has_coupon,
            )
            if not is_valid:
                logger.info(
                    f"[Just-in-Time] Oferta #{queue_id} descartada antes de publicar ({reason}): {item.get('title')}"
                )
                database.mark_queue_item_failed(queue_id)
                continue

            if live_price and live_price > 0 and not has_coupon and abs(live_price - expected_price) >= 0.50:
                item["price"] = live_price
                if live_orig and live_orig > live_price:
                    item["original_price"] = live_orig
                    item["discount_pct"] = round(((live_orig - live_price) / live_orig) * 100)
                database.update_queue_item_price(queue_id, live_price, live_orig)

        success = await publish_offer(bot, item, database=database)
        if success:
            database.mark_queue_item_sent(
                queue_id,
                message_id=item.get("_sent_message_id"),
                thread_id=item.get("_sent_thread_id"),
                has_photo=bool(item.get("_sent_has_photo")),
                caption_html=item.get("_sent_caption_html"),
            )
            return True
        else:
            database.mark_queue_item_failed(queue_id)
            return False

    return False


async def check_and_mark_expired_offers(
    bot: Bot,
    database: DatabaseManager = db,
) -> int:
\
\
\
\

    chat_id = database.get_chat_id()
    if not chat_id:
        return 0

    recent_items = database.get_recent_posted_for_expiration_check(hours=2, limit=6)
    if not recent_items:
        return 0

    from scrapers.ml_offers import validate_live_offer_status

    marked_count = 0
    for row in recent_items:
        check_url = str(row.get("original_url") or row.get("affiliate_url") or "")
        price = float(row.get("price") or 0.0)
        msg_id = row.get("message_id")
        if not check_url or not msg_id:
            continue

        is_valid, live_price, _, reason = await validate_live_offer_status(
            check_url,
            expected_price=price,
            has_coupon=False,
            max_price_jump_pct=20.0,
        )
        if is_valid:
            continue

        old_caption = str(row.get("caption_html") or "")
        if not old_caption:
            old_caption = format_offer_message(row)

        if "OFERTA ENCERRADA" in old_caption:
            database.mark_posted_offer_expired(str(row["offer_key"]))
            continue

        expired_banner = "🔴 <b>[OFERTA ENCERRADA / PREÇO SUBIU]</b>\n"
        new_caption = expired_banner + old_caption

        try:
            if row.get("has_photo"):
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=int(msg_id),
                    caption=new_caption[:1024],
                    parse_mode=ParseMode.HTML,
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(msg_id),
                    text=new_caption[:4096],
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            database.mark_posted_offer_expired(str(row["offer_key"]))
            marked_count += 1
            logger.info(
                f"[Detector Acabou!] Oferta marcada como encerrada no Telegram (msg_id={msg_id}, motivo={reason}): {row.get('title')}"
            )
        except TelegramError as exc:
            logger.debug(f"Não foi possível editar mensagem expirada {msg_id}: {exc}")
            database.mark_posted_offer_expired(str(row["offer_key"]))


    raw_del_hours = database.get_config("delete_expired_after_hours")
    try:
        del_hours = (
            int(raw_del_hours)
            if raw_del_hours is not None
            else settings.delete_expired_after_hours
        )
    except ValueError:
        del_hours = settings.delete_expired_after_hours

    if del_hours >= 0:
        to_delete = database.get_expired_offers_for_deletion(
            older_than_hours=del_hours, limit=8
        )
        for exp_row in to_delete:
            exp_msg_id = exp_row.get("message_id")
            exp_key = str(exp_row.get("offer_key") or "")
            if exp_msg_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=int(exp_msg_id))
                    logger.info(
                        f"[Auto-Limpeza] Mensagem de oferta encerrada apagada do tópico (msg_id={exp_msg_id}): {exp_row.get('title')}"
                    )
                except TelegramError:
                    pass
            database.mark_posted_offer_deleted(exp_key)

    return marked_count


async def publish_daily_admin_report(
    bot: Bot,
    database: DatabaseManager = db,
) -> bool:
\
\
\

    report = database.get_24h_operational_report()
    report_html = format_operational_report(report)

    target_chat = database.get_config("admin_private_chat_id") or database.get_chat_id()
    if not target_chat:
        return False

    try:
        await bot.send_message(
            chat_id=int(target_chat),
            text=report_html,
            parse_mode=ParseMode.HTML,
            disable_notification=True,
        )
        logger.info("Relatório Diário de Performance Operacional (24h) enviado com sucesso.")
        return True
    except TelegramError as exc:
        logger.warning(f"Falha ao enviar Relatório Operacional: {exc}")
        return False
