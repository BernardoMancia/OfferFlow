from __future__ import annotations

import html
from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import settings
from database.db import db
from telegram_bot.admin_handlers import _check_command_admin
from telegram_bot.price_chart import generate_price_history_card
from telegram_bot.setup_topics import is_user_admin


async def _allow_member_dm_or_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    chat = update.effective_chat
    if not chat:
        return False
    if chat.type == ChatType.PRIVATE:
        return True
    return await _check_command_admin(update, context)


async def cmd_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _allow_member_dm_or_admin(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    configured_group_id = db.get_chat_id()
    is_admin = bool(
        configured_group_id
        and await is_user_admin(context.bot, int(configured_group_id), user.id)
    )

    lines = [
        "🔥 <b>Bem-vindo ao Assistente Oficial do Canal de Promoções!</b>",
        "",
        "🔔 <b>Alertas Pessoais de Promoções (Radar no Privado):</b>",
        "• <code>/alerta rtx 4060 1900</code> — Avisa quando aparecer por até R$ 1.900",
        "• <code>/alerta milka</code> — Avisa qualquer oferta com a palavra <i>milka</i>",
        "• <code>/meus_alertas</code> — Lista e remove seus alertas ativos",
        "",
        "📊 <b>Gráfico de Histórico de Preços:</b>",
        "• <code>/historico airfryer</code> — Gera o gráfico PNG de evolução de preço",
    ]
    if settings.web_public_url:
        lines.extend(
            [
                "",
                f"🌐 <b>Vitrine Web Interativa:</b> {html.escape(settings.web_public_url)}",
            ]
        )
    if is_admin:
        db.set_config("admin_private_chat_id", str(message.chat_id))
        lines.extend(
            [
                "",
                "──────────────────────",
                "👑 <b>Comandos de Administrador:</b>",
                "• <code>/painel</code> — Painel Interativo de Controle",
                "• <code>/relatorio</code> — Relatório Operacional 24h",
                "• <code>/afiliado</code> e <code>/cookie</code> — Credenciais de Afiliados",
                "• <b>Dica:</b> Cole qualquer link de produto aqui para gerar uma prévia interativa!",
            ]
        )

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_alerta(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _allow_member_dm_or_admin(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if not context.args:
        await message.reply_text(
            "🔔 <b>Como criar um Alerta Pessoal de Oferta:</b>\n\n"
            "• <b>Qualquer preço:</b>\n"
            "<code>/alerta chocolate milka</code>\n\n"
            "• <b>Com teto máximo de preço:</b>\n"
            "<code>/alerta rtx 4060 1900</code>\n"
            "<code>/alerta airfryer 300</code>\n\n"
            "Assim que o Bot publicar uma oferta compatível no grupo, você receberá um aviso instantâneo aqui no privado!",
            parse_mode=ParseMode.HTML,
        )
        return

    args = list(context.args)
    max_price = None
    if len(args) >= 2:
        last_token = (
            args[-1]
            .replace("R$", "")
            .replace("r$", "")
            .replace(".", "")
            .replace(",", ".")
            .strip()
        )
        try:
            parsed_price = float(last_token)
            if parsed_price > 0:
                max_price = parsed_price
                args = args[:-1]
        except ValueError:
            pass

    keyword = " ".join(args).strip()
    if len(keyword) < 2:
        await message.reply_text(
            "⚠️ Informe uma palavra-chave com pelo menos 2 caracteres. Exemplo: <code>/alerta milka</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    alert_id = db.add_user_alert(user.id, keyword, max_price=max_price)
    if alert_id is None:
        await message.reply_text(
            "⚠️ Você atingiu o limite máximo de <b>15 alertas ativos</b>. Use <code>/meus_alertas</code> para gerenciar.",
            parse_mode=ParseMode.HTML,
        )
        return

    price_info = f" (teto: <b>R$ {max_price:.2f}</b>)" if max_price else " (qualquer preço em promoção)"
    await message.reply_text(
        f"✅ <b>Alerta #{alert_id} cadastrado com sucesso!</b>\n"
        f"🔎 <b>Termo:</b> <code>{html.escape(keyword)}</code>{price_info}\n\n"
        "Use <code>/meus_alertas</code> para ver ou excluir seus alertas.",
        parse_mode=ParseMode.HTML,
    )


def _build_user_alerts_view(user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    alerts = db.list_user_alerts(user_id)
    if not alerts:
        return (
            "📭 <b>Você ainda não possui alertas ativos.</b>\n\n"
            "Crie um agora mesmo usando:\n"
            "• <code>/alerta milka</code>\n"
            "• <code>/alerta rtx 4060 1900</code>",
            None,
        )

    lines = [
        f"🔔 <b>Seus Alertas Pessoais Ativos ({len(alerts)}/15):</b>",
        "",
    ]
    kb_rows: List[List[InlineKeyboardButton]] = []
    for a in alerts:
        aid = int(a["id"])
        kw = html.escape(str(a["keyword"]))
        mp = a.get("max_price")
        mp_str = f" — até <b>R$ {float(mp):.2f}</b>" if mp is not None else " — <i>qualquer preço</i>"
        lines.append(f"• <b>#{aid}</b>: <code>{kw}</code>{mp_str}")
        kb_rows.append(
            [
                InlineKeyboardButton(
                    f"🗑️ Remover #{aid} ({str(a['keyword'])[:22]})",
                    callback_data=f"rmalert:{aid}",
                )
            ]
        )

    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)


async def cmd_meus_alertas(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _allow_member_dm_or_admin(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    text, kb = _build_user_alerts_view(user.id)
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cmd_remover_alerta(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _allow_member_dm_or_admin(update, context):
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if not context.args or not context.args[0].isdigit():
        await message.reply_text(
            "ℹ️ Uso: <code>/remover_alerta ID</code> (ou use os botões em <code>/meus_alertas</code>).",
            parse_mode=ParseMode.HTML,
        )
        return

    alert_id = int(context.args[0])
    ok = db.remove_user_alert(user.id, alert_id)
    if ok:
        await message.reply_text(
            f"🗑️ <b>Alerta #{alert_id} removido com sucesso!</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "⚠️ Alerta não encontrado ou já removido.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_historico(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _allow_member_dm_or_admin(update, context):
        return
    message = update.effective_message
    if not message:
        return

    if not context.args:
        await message.reply_text(
            "📊 <b>Gráfico de Histórico de Preços</b>\n\n"
            "Informe o nome ou código do produto para gerar o gráfico:\n"
            "• <code>/historico milka</code>\n"
            "• <code>/historico airfryer</code>\n"
            "• <code>/historico rtx 4060</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    query_str = " ".join(context.args).strip()
    points = db.get_offer_price_points(query_str)
    if not points:
        await message.reply_text(
            f"📭 Nenhum histórico encontrado para <code>{html.escape(query_str)}</code> ainda.",
            parse_mode=ParseMode.HTML,
        )
        return

    title_str = str(points[-1].get("title") or query_str)
    prices = [float(p["price"]) for p in points if p.get("price") is not None]
    min_price = min(prices)
    avg_price = sum(prices) / len(prices)
    current_price = prices[-1]

    png_bytes = generate_price_history_card(title_str, points)
    caption_lines = [
        f"📊 <b>Histórico de Preços — {html.escape(title_str[:85])}</b>",
        "",
        f"🟢 <b>Menor Preço Registrado:</b> R$ {min_price:.2f}",
        f"🔵 <b>Preço Médio:</b> R$ {avg_price:.2f}",
        f"🏷️ <b>Último Preço:</b> R$ {current_price:.2f}",
    ]
    await message.reply_photo(
        photo=png_bytes,
        caption="\n".join(caption_lines),
        parse_mode=ParseMode.HTML,
    )
