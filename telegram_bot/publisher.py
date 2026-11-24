from __future__ import annotations

import html
import time
from datetime import datetime
from typing import Any, Dict, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from affiliate.mercadolivre import consume_ml_cookie_expired_alert, is_monetized_ml_url
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
)

logger = get_logger("telegram.publisher")


def _parse_hhmm(value: str, default_h: int, default_m: int) -> int:
    try:
        parts = value.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return default_h * 60 + default_m


def is_quiet_hours(now: Optional[datetime] = None) -> bool:
    dt = now or datetime.now()
    current_min = dt.hour * 60 + dt.minute
    start_min = _parse_hhmm(settings.quiet_hours_start, 23, 30)
    end_min = _parse_hhmm(settings.quiet_hours_end, 7, 30)

    if start_min <= end_min:
        return start_min <= current_min < end_min

    return current_min >= start_min or current_min < end_min


async def _notify_if_ml_cookie_expired(bot: Bot, database: DatabaseManager) -> None:
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

    target = database.get_config("admin_private_chat_id")
    if not target:
        return

    database.set_config("last_ml_cookie_alert_ts", str(now_ts))
    try:
        await bot.send_message(
            chat_id=int(target),
            text=(
                "⚠️ <b>Aviso de Manutenção (Afiliado ML):</b>\n"
                "O seu <code>ML_AFFILIATE_COOKIE</code> parece ter expirado ao gerar link curto <code>/sec/</code>.\n\n"
                "✅ <b>Fique tranquilo:</b> O Bot ativou automaticamente o <b>Fallback Oficial</b> "
                "(<code>matt_tool</code> / <code>matt_word</code>) e todas as postagens continuam monetizadas!\n"
                "💡 <i>Quando puder, atualize via <code>/cookie</code> para voltar a usar links curtos <code>/sec/</code>.</i>"
            ),
            parse_mode=ParseMode.HTML,
            disable_notification=True,
        )
    except TelegramError as exc:
        logger.warning(f"Não foi possível enviar alerta de cookie ML expirado: {exc}")


def _resolve_hub_url(database: DatabaseManager) -> str:
    hub = database.get_hub_channel()
    if hub:
        if hub.get("invite_url"):
            return str(hub["invite_url"])
        if hub.get("username"):
            return f"https://t.me/{hub['username']}"
    return database.get_folder_url() or settings.telegram_group_invite_url or ""


async def _resolve_publish_target(
    bot: Bot,
    topic_key: str,
    database: DatabaseManager,
) -> tuple[Optional[int], Optional[int], bool]:
    channel_chat_id = database.get_channel_chat_id(topic_key)
    if channel_chat_id:
        return channel_chat_id, None, True

    if database.get_linked_category_keys():
        fallback_bugs_id = database.get_channel_chat_id("ofertas_bugs")
        if fallback_bugs_id:
            return fallback_bugs_id, None, True
        return None, None, True

    group_chat_id = database.get_chat_id()
    if not group_chat_id:
        return None, None, False

    thread_id = database.get_topic_thread_id(topic_key)
    if thread_id is None:
        await ensure_forum_topics(bot, group_chat_id, database=database)
        thread_id = database.get_topic_thread_id(topic_key)
    return group_chat_id, thread_id, False


async def publish_offer(
    bot: Bot,
    offer: Dict[str, Any],
    database: DatabaseManager = db,
) -> bool:
    aff_url = str(offer.get("affiliate_url") or "")
    if settings.require_affiliate_link and not is_monetized_ml_url(aff_url):
        logger.warning(
            f"Publicação bloqueada pela Trava de Monetização: link sem afiliado ML ({aff_url}). "
            "Use /configurar_afiliado <seu_link_ml>."
        )
        return False

    topic_key = str(offer.get("topic_key") or "ofertas_bugs")
    target_chat_id, thread_id, is_channel = await _resolve_publish_target(
        bot, topic_key, database
    )
    if not target_chat_id:
        logger.warning(
            f"Nenhum canal vinculado para [{topic_key}]. Use /vincular {topic_key} dentro do canal no Telegram."
        )
        return False

    await _notify_if_ml_cookie_expired(bot, database)

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

    hub_url = _resolve_hub_url(database)
    caption = format_offer_message(offer_payload)
    keyboard = build_offer_keyboard(offer_payload, hub_url=hub_url)
    image_url = (offer_payload.get("image_url") or "").strip()

    discount_pct = int(offer_payload.get("discount_pct") or 0)
    silent_mode = is_quiet_hours() and discount_pct < 60

    async def _send(dest_chat_id: int, target_thread_id: int | None, use_photo: bool) -> bool:
        kwargs: Dict[str, Any] = {
            "chat_id": dest_chat_id,
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
            offer["_sent_chat_id"] = dest_chat_id
            offer["_sent_message_id"] = sent_msg.message_id
            offer["_sent_thread_id"] = target_thread_id
            offer["_sent_has_photo"] = used_photo
            offer["_sent_caption_html"] = caption

        if discount_pct >= 60 and topic_key == "ofertas_bugs" and sent_msg:
            try:
                await bot.pin_chat_message(
                    chat_id=dest_chat_id,
                    message_id=sent_msg.message_id,
                    disable_notification=True,
                )
                logger.info(
                    f"Super Desconto ({discount_pct}% OFF) fixado automaticamente em [{topic_key}] (msg_id={sent_msg.message_id})."
                )
            except TelegramError as pin_exc:
                logger.debug(f"Não foi possível fixar Super Desconto: {pin_exc}")

        return True

    try:
        await _send(target_chat_id, thread_id, use_photo=bool(image_url))
        logger.info(
            f"Oferta publicada em [{topic_key}] (chat={target_chat_id}, channel={is_channel}, silent={silent_mode}): "
            f"{offer_payload.get('title')} - R$ {offer_payload.get('price')}"
        )
        await _notify_matched_user_alerts(
            bot,
            offer_payload=offer_payload,
            dest_chat_id=target_chat_id,
            sent_message_id=offer.get("_sent_message_id") if isinstance(offer, dict) else None,
            sent_thread_id=thread_id,
            database=database,
        )
        return True

    except BadRequest as exc:
        err_msg = str(exc).lower()

        if not is_channel and ("thread not found" in err_msg or "message_thread_id" in err_msg):
            new_thread_id = await recreate_single_topic(
                bot, target_chat_id, topic_key, database=database
            )
            if new_thread_id:
                try:
                    await _send(target_chat_id, new_thread_id, use_photo=bool(image_url))
                    return True
                except TelegramError:
                    await _send(target_chat_id, new_thread_id, use_photo=False)
                    return True

        if image_url:
            logger.warning(
                f"Falha ao enviar foto ({image_url}): {exc}. Enviando oferta apenas como texto HTML."
            )
            try:
                await _send(target_chat_id, thread_id, use_photo=False)
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
    dest_chat_id: int,
    sent_message_id: Optional[int],
    sent_thread_id: Optional[int],
    database: DatabaseManager = db,
) -> int:
    title = str(offer_payload.get("title") or "")
    price_num = float(offer_payload.get("price") or 0.0)
    matches = database.match_user_alerts(title, price=price_num if price_num > 0 else None)
    if not matches:
        return 0

    price_str = format_brl(price_num)
    aff_url = str(offer_payload.get("affiliate_url") or offer_payload.get("original_url") or "")
    topic_key = str(offer_payload.get("topic_key") or "ofertas_bugs")
    topic_label = OFFICIAL_TOPICS.get(topic_key, topic_key)

    post_url = None
    ch = database.get_channel(topic_key)
    if ch and ch.get("username") and sent_message_id:
        post_url = f"https://t.me/{ch['username']}/{sent_message_id}"
    else:
        str_chat = str(dest_chat_id)
        if str_chat.startswith("-100") and sent_message_id:
            clean_cid = str_chat[4:]
            if sent_thread_id:
                post_url = f"https://t.me/c/{clean_cid}/{sent_thread_id}/{sent_message_id}"
            else:
                post_url = f"https://t.me/c/{clean_cid}/{sent_message_id}"

    notified = 0
    for alert in matches:
        kw = html.escape(str(alert.get("keyword") or ""))
        target_chat_id = int(alert["chat_id"])
        text = (
            f"🔔 <b>ALERTA DE DESEJO ATINGIDO!</b> (<code>{kw}</code>)\n\n"
            f"📦 <b>{html.escape(title)}</b>\n"
            f"🔥 <b>Por:</b> <b>{price_str}</b>\n"
            f"📂 <b>Canal:</b> {topic_label}\n"
        )
        buttons = [[InlineKeyboardButton("🛒 Garantir no Mercado Livre", url=aff_url)]]
        if post_url:
            buttons[0].append(InlineKeyboardButton("📢 Ver no Canal", url=post_url))

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
    if database.is_paused():
        return False

    top_offers = database.get_top_offers_last_24h(limit=5)
    if not top_offers:
        return False

    dest_chat_id: Optional[int] = database.get_channel_chat_id("hub")
    thread_id: Optional[int] = None
    if not dest_chat_id:
        dest_chat_id = database.get_channel_chat_id("ofertas_bugs")
    if not dest_chat_id:
        dest_chat_id = database.get_chat_id()
        if dest_chat_id:
            thread_id = database.get_topic_thread_id("ofertas_bugs")

    if not dest_chat_id:
        return False

    summary_html = format_daily_top5_summary(top_offers)
    kwargs: Dict[str, Any] = {
        "chat_id": dest_chat_id,
        "text": summary_html,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
    }
    if thread_id is not None:
        kwargs["message_thread_id"] = thread_id

    try:
        await bot.send_message(**kwargs)
        logger.info(f"Resumo Diário Top 5 publicado em chat_id={dest_chat_id} ({len(top_offers)} ofertas).")
        return True
    except TelegramError as exc:
        logger.error(f"Falha ao publicar Resumo Diário Top 5: {exc}")
        return False


async def check_and_mark_expired_offers(
    bot: Bot,
    database: DatabaseManager = db,
) -> int:
    from scrapers.ml_offers import validate_live_offer_status

    fallback_chat_id = database.get_chat_id()
    recent_posts = database.get_recent_posted_for_expiration_check(hours=2, limit=6)
    expired_count = 0

    for item in recent_posts:
        dest_chat_id = item.get("target_chat_id") or fallback_chat_id
        check_url = item.get("original_url") or item.get("affiliate_url")
        msg_id = item.get("message_id")
        if not dest_chat_id or not check_url or not msg_id:
            continue

        is_valid, live_price, _, reason = await validate_live_offer_status(
            url=str(check_url),
            expected_price=float(item["price"]),
            has_coupon=False,
            max_price_jump_pct=22.0,
        )
        if is_valid:
            continue

        title_safe = html.escape(str(item.get("title") or "Oferta"))
        old_p = format_brl(float(item["price"]))
        new_p_note = f" (preço atual: {format_brl(live_price)})" if live_price else ""
        expired_html = (
            f"🔴 <b>OFERTA ENCERRADA / ESGOTADA</b>\n\n"
            f"<s>{title_safe}</s>\n"
            f"<s>Estava por {old_p}</s>{new_p_note}\n\n"
            f"⚠️ <i>Esta promoção já foi encerrada ou teve alteração de preço na loja.</i>"
        )
        try:
            if item.get("has_photo"):
                await bot.edit_message_caption(
                    chat_id=int(dest_chat_id),
                    message_id=int(msg_id),
                    caption=expired_html,
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
            else:
                await bot.edit_message_text(
                    chat_id=int(dest_chat_id),
                    message_id=int(msg_id),
                    text=expired_html,
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
            database.mark_posted_offer_expired(str(item["offer_key"]))
            expired_count += 1
            logger.info(
                f"Oferta encerrada marcada em chat={dest_chat_id} (msg_id={msg_id}, motivo={reason}): {item['title']}"
            )
        except TelegramError as exc:
            logger.debug(f"Não foi possível editar oferta encerrada msg_id={msg_id}: {exc}")
            database.mark_posted_offer_expired(str(item["offer_key"]))

    del_hours_raw = database.get_config("delete_expired_after_hours")
    try:
        del_hours = int(del_hours_raw) if del_hours_raw is not None else settings.delete_expired_after_hours
    except ValueError:
        del_hours = settings.delete_expired_after_hours

    if del_hours >= 0:
        old_expired = database.get_expired_offers_for_deletion(
            older_than_hours=del_hours, limit=10
        )
        for exp_item in old_expired:
            dest_chat_id = exp_item.get("target_chat_id") or fallback_chat_id
            msg_id = exp_item.get("message_id")
            if not dest_chat_id or not msg_id:
                continue
            try:
                await bot.delete_message(chat_id=int(dest_chat_id), message_id=int(msg_id))
                logger.info(
                    f"Auto-limpeza: mensagem encerrada apagada (chat={dest_chat_id}, msg_id={msg_id}): {exp_item['title']}"
                )
            except TelegramError as exc:
                logger.debug(f"Falha ao apagar oferta encerrada msg_id={msg_id}: {exc}")
            database.mark_posted_offer_deleted(str(exp_item["offer_key"]))

    return expired_count


async def publish_daily_admin_report(
    bot: Bot,
    database: DatabaseManager = db,
) -> bool:
    admin_dm = database.get_config("admin_private_chat_id")
    if not admin_dm:
        return False

    report = database.get_24h_operational_report()
    html_text = format_operational_report(report)
    try:
        await bot.send_message(
            chat_id=int(admin_dm),
            text=html_text,
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"Relatório Operacional 24h enviado ao Admin (chat_id={admin_dm}).")
        return True
    except TelegramError as exc:
        logger.warning(f"Falha ao enviar Relatório Operacional 24h ao Admin: {exc}")
        return False


async def process_next_queued_offer(
    bot: Bot,
    database: DatabaseManager = db,
) -> bool:
    if database.is_paused():
        logger.debug("Publicação automática pausada pelo administrador (/pausar).")
        return False

    has_channels = bool(database.get_linked_category_keys())
    if not has_channels and not database.get_chat_id():
        return False

    from scrapers.ml_offers import validate_live_offer_status

    for _ in range(3):
        offer = database.get_next_pending_offer(only_linked_channels=has_channels)
        if not offer:
            return False

        queue_id = int(offer["id"])
        check_url = offer.get("original_url") or offer.get("affiliate_url")
        if check_url:
            is_valid, live_price, live_orig, reason = await validate_live_offer_status(
                url=str(check_url),
                expected_price=float(offer["price"]),
                has_coupon=bool(offer.get("coupon")),
            )
            if not is_valid:
                database.mark_queue_item_failed(queue_id)
                logger.info(
                    f"[Just-in-Time] Oferta #{queue_id} descartada antes de postar ({reason}): {offer['title']}"
                )
                continue
            if (
                live_price
                and live_price > 0
                and abs(live_price - float(offer["price"])) >= 1.0
                and not offer.get("coupon")
            ):
                orig_val = live_orig or offer.get("original_price")
                database.update_queue_item_price(queue_id, live_price, orig_val)
                offer["price"] = live_price
                if orig_val and orig_val > live_price:
                    offer["original_price"] = orig_val
                    offer["discount_pct"] = round(((orig_val - live_price) / orig_val) * 100)

        ok = await publish_offer(bot, offer, database=database)
        if ok:
            database.mark_queue_item_sent(
                queue_id,
                message_id=offer.get("_sent_message_id"),
                thread_id=offer.get("_sent_thread_id"),
                has_photo=bool(offer.get("_sent_has_photo")),
                caption_html=offer.get("_sent_caption_html"),
                target_chat_id=offer.get("_sent_chat_id"),
            )
            return True
        else:
            database.mark_queue_item_failed(queue_id)
            return False

    return False
