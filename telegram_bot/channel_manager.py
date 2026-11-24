from __future__ import annotations

import html
import unicodedata
from pathlib import Path
from typing import Optional

from telegram import Bot, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from affiliate.mercadolivre import (
    build_fallback_affiliate_url,
    extract_affiliate_params_from_url,
    has_active_ml_affiliate,
)
from classifier.catalogs import (
    BOT_BRAND_NAME,
    BOT_DISPLAY_NAME,
    CHANNEL_CATALOG,
    OFFICIAL_TOPICS,
)
from database.db import DatabaseManager, db
from database.logger import get_logger
from telegram_bot.formatter import (
    build_hub_directory_keyboard,
    format_hub_directory_message,
)

logger = get_logger("telegram.channel_manager")
CHANNEL_AVATARS_DIR = Path(__file__).resolve().parent.parent / "assets" / "channel_avatars"


def get_channel_avatar_path(category_key: str) -> Optional[Path]:
    clean = category_key.strip().lower()
    for ext in (".jpg", ".png", ".jpeg"):
        candidate = CHANNEL_AVATARS_DIR / f"{clean}{ext}"
        if candidate.is_file():
            return candidate
    return None


async def apply_channel_photo(bot: Bot, chat_id: int, category_key: str) -> bool:
    avatar_path = get_channel_avatar_path(category_key)
    if not avatar_path:
        return False
    try:
        photo_bytes = avatar_path.read_bytes()
        await bot.set_chat_photo(chat_id=chat_id, photo=photo_bytes)
        return True
    except TelegramError as exc:
        logger.debug(f"Não foi possível definir foto do canal {chat_id} ({category_key}): {exc}")
        return False


def _normalize_match_text(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def infer_category_key_from_chat(
    title: Optional[str], username: Optional[str] = None
) -> Optional[str]:
    joined = _normalize_match_text(f"{title or ''} {username or ''}")
    if not joined.strip():
        return None
    rules = (
        ("hub", ("comunidade", "hub", "offerflowml")),
        ("ofertas_bugs", ("relampago", "bugs", "offerflowofertas", "offerflowbugs")),
        ("tech_celulares", ("tech", "informatica", "celular")),
        ("games_geek", ("games", "brinquedo", "livro", "geek")),
        ("casa_eletro", ("casa", "eletro", "cozinha")),
        ("ferramentas_construcao", ("ferramenta", "construcao", "obra")),
        ("moda_relogios", ("moda", "calcado", "relogio")),
        ("beleza_esportes", ("beleza", "saude", "esporte", "fitness")),
        ("pet_bebes_papelaria", ("pet", "bebe", "papelaria")),
    )
    for key, markers in rules:
        if any(m in joined for m in markers):
            return key
    return None


async def configure_bot_profile(bot: Bot) -> None:
    commands = [
        BotCommand("start", "Menu principal da Comunidade OfferFlow"),
        BotCommand("alerta", "Criar alerta pessoal de oferta (ex: /alerta rtx 4060 1900)"),
        BotCommand("meus_alertas", "Listar ou remover seus alertas pessoais"),
        BotCommand("historico", "Gerar gráfico de histórico de preços"),
        BotCommand("painel", "[Admin] Painel interativo de controle"),
        BotCommand("canais", "[Admin] Status dos 8 canais e Comunidade Hub"),
        BotCommand("guia_configuracao", "[Admin] Guia rápido de configuração"),
        BotCommand("configurar_afiliado", "[Admin] Extrair afiliado ML de um link seu"),
        BotCommand("pasta", "[Admin] Definir link da Pasta de Canais do Telegram"),
        BotCommand("relatorio", "[Admin] Relatório operacional das últimas 24h"),
    ]
    try:
        await bot.set_my_commands(commands)
    except TelegramError as exc:
        logger.debug(f"Falha ao registrar comandos do Bot: {exc}")
    try:
        await bot.set_my_short_description(
            short_description=(
                "⚡ Curadoria automática 100% Mercado Livre • Alertas de preço, cupons e ofertas verificadas da Comunidade OfferFlow."
            )
        )
    except TelegramError as exc:
        logger.debug(f"Falha ao definir short_description do Bot: {exc}")
    try:
        await bot.set_my_description(
            description=(
                "⚡ Bem-vindo ao OfferFlow! Crie alertas personalizados de preço, consulte gráficos de histórico "
                "e acompanhe as melhores ofertas verificadas do Mercado Livre nos canais da Comunidade OfferFlow."
            )
        )
    except TelegramError as exc:
        logger.debug(f"Falha ao definir description do Bot: {exc}")


async def _resolve_channel_invite_url(bot: Bot, chat_id: int) -> tuple[Optional[str], Optional[str]]:
    username = None
    invite_url = None
    try:
        chat = await bot.get_chat(chat_id)
        if chat.username:
            username = chat.username
            invite_url = f"https://t.me/{chat.username}"
        else:
            invite_url = chat.invite_link
            if not invite_url:
                try:
                    invite_url = await bot.export_chat_invite_link(chat_id)
                except TelegramError:
                    invite_url = None
    except TelegramError as exc:
        logger.debug(f"Erro ao obter convite do canal {chat_id}: {exc}")
    return username, invite_url


async def refresh_hub_directory(
    bot: Bot, database: DatabaseManager = db
) -> bool:
    hub = database.get_hub_channel()
    if not hub or not hub.get("chat_id"):
        return False

    hub_chat_id = int(hub["chat_id"])
    channels = database.get_all_channels(include_hub=False)
    folder_url = database.get_folder_url()
    text = format_hub_directory_message(channels, folder_url=folder_url)
    kb = build_hub_directory_keyboard(channels, folder_url=folder_url)

    pinned_id = hub.get("pinned_msg_id")
    if pinned_id:
        try:
            await bot.edit_message_text(
                chat_id=hub_chat_id,
                message_id=int(pinned_id),
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=kb if kb.inline_keyboard else None,
            )
            return True
        except TelegramError as exc:
            if "message is not modified" in str(exc).lower():
                return True

    try:
        sent = await bot.send_message(
            chat_id=hub_chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=kb if kb.inline_keyboard else None,
        )
        database.set_channel_pinned_msg("hub", sent.message_id)
        try:
            await bot.pin_chat_message(
                chat_id=hub_chat_id,
                message_id=sent.message_id,
                disable_notification=True,
            )
        except TelegramError:
            pass
        return True
    except TelegramError as exc:
        logger.warning(f"Falha ao atualizar diretório da Comunidade Hub: {exc}")
        return False


async def bind_and_style_channel(
    bot: Bot,
    chat_id: int,
    category_key: str,
    database: DatabaseManager = db,
) -> tuple[bool, str]:
    clean_key = category_key.strip().lower()
    if clean_key not in CHANNEL_CATALOG:
        valid = ", ".join(CHANNEL_CATALOG.keys())
        return False, f"Chave inválida. Chaves aceitas: {valid}"

    spec = CHANNEL_CATALOG[clean_key]

    try:
        await bot.set_chat_title(chat_id=chat_id, title=spec["title"])
    except TelegramError as exc:
        logger.debug(f"Não foi possível renomear canal {chat_id}: {exc}")

    try:
        await bot.set_chat_description(chat_id=chat_id, description=spec["description"])
    except TelegramError as exc:
        logger.debug(f"Não foi possível definir descrição do canal {chat_id}: {exc}")

    await apply_channel_photo(bot, chat_id, clean_key)

    username, invite_url = await _resolve_channel_invite_url(bot, chat_id)
    database.bind_channel(
        category_key=clean_key,
        chat_id=chat_id,
        username=username,
        invite_url=invite_url,
    )

    if clean_key == "hub":
        await refresh_hub_directory(bot, database=database)
        return True, f"Comunidade Hub '{spec['title']}' vinculada e diretório fixado!"

    hub = database.get_hub_channel()
    hub_url = ""
    if hub:
        hub_url = str(hub.get("invite_url") or (f"https://t.me/{hub['username']}" if hub.get("username") else ""))

    kb = None
    if hub_url.startswith("http"):
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"⚡ Voltar para Comunidade {BOT_BRAND_NAME}", url=hub_url)]]
        )

    existing = database.get_channel(clean_key)
    if not existing or not existing.get("pinned_msg_id"):
        try:
            welcome_msg = await bot.send_message(
                chat_id=chat_id,
                text=spec["welcome_text"],
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            database.set_channel_pinned_msg(clean_key, welcome_msg.message_id)
            try:
                await bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=welcome_msg.message_id,
                    disable_notification=True,
                )
            except TelegramError:
                pass
        except TelegramError as exc:
            logger.debug(f"Não foi possível enviar boas-vindas no canal {chat_id}: {exc}")

    await refresh_hub_directory(bot, database=database)
    return True, f"Canal '{spec['title']}' vinculado com sucesso e listado na Comunidade Hub!"


async def auto_bind_channel_if_matched(
    bot: Bot,
    chat_id: int,
    title: Optional[str],
    username: Optional[str] = None,
    database: DatabaseManager = db,
) -> tuple[bool, str]:
    cat_key = infer_category_key_from_chat(title, username)
    if not cat_key:
        return False, "Canal não corresponde automaticamente a nenhuma categoria planejada."
    return await bind_and_style_channel(bot, chat_id, cat_key, database=database)


async def handle_channel_post_commands(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    post = update.channel_post
    if not post or not post.chat or post.chat.type != ChatType.CHANNEL:
        return

    text = (post.text or "").strip()
    if not text.startswith("/"):
        return

    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    args = parts[1:]

    if cmd in ("/vincular", "/bind"):
        if not args:
            return
        cat_key = args[0].strip().lower()
        ok, status_msg = await bind_and_style_channel(
            context.bot, post.chat.id, cat_key, database=db
        )
        try:
            await post.delete()
        except TelegramError:
            pass
        admin_dm = db.get_config("admin_private_chat_id")
        if admin_dm:
            try:
                prefix = "✅" if ok else "❌"
                await context.bot.send_message(
                    chat_id=int(admin_dm),
                    text=f"{prefix} <b>{html.escape(status_msg)}</b>",
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError:
                pass
    elif cmd in ("/atualizar_hub", "/refresh_hub"):
        try:
            await post.delete()
        except TelegramError:
            pass
        await refresh_hub_directory(context.bot, database=db)
    elif cmd == "/pasta" and args:
        folder_url = args[0].strip()
        db.set_folder_url(folder_url)
        try:
            await post.delete()
        except TelegramError:
            pass
        await refresh_hub_directory(context.bot, database=db)


def build_channels_status_text(database: DatabaseManager = db) -> str:
    channels = database.get_all_channels(include_hub=True)
    folder_url = database.get_folder_url()
    aff_ok = has_active_ml_affiliate()

    lines = [
        f"📢 <b>MAPA DE CANAIS & COMUNIDADE • {BOT_BRAND_NAME.upper()}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Afiliado Mercado Livre:</b> {'✅ ATIVO (100% monetizado)' if aff_ok else '🔴 PENDENTE — envie /configurar_afiliado <seu_link_ml>'}",
        f"📂 <b>Pasta do Telegram:</b> {html.escape(folder_url) if folder_url else '<i>Opcional — use /pasta https://t.me/addlist/...</i>'}",
        "",
    ]

    for ch in channels:
        key = str(ch["category_key"])
        spec = CHANNEL_CATALOG.get(key) or {}
        emoji = spec.get("emoji", "📌")
        title = spec.get("title", key)
        if ch.get("chat_id"):
            link_str = ch.get("invite_url") or f"id {ch['chat_id']}"
            lines.append(f"✅ <b>{html.escape(title)}</b>\n   ↳ <code>{key}</code> • {html.escape(str(link_str))}")
        else:
            lines.append(f"⬜ <b>{html.escape(title)}</b>\n   ↳ Crie o canal, adicione o Bot como Admin e poste: <code>/vincular {key}</code>")

    return "\n".join(lines)


def build_setup_guide_text() -> str:
    lines = [
        f"🧭 <b>GUIA RÁPIDO DE CONFIGURAÇÃO • {BOT_DISPLAY_NAME.upper()}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>1️⃣ Ativar seu Link de Afiliado Mercado Livre (30 seg):</b>",
        "• Gere <b>qualquer link de afiliado</b> na sua Barra de Afiliados do Mercado Livre (pode ser link curto <code>/sec/...</code> ou URL completa).",
        "• Envie aqui no privado:",
        "<code>/configurar_afiliado COLE_SEU_LINK_AQUI</code>",
        "<i>O Bot extrai seu matt_tool e matt_word automaticamente e ativa a trava de 100% monetização!</i>",
        "",
        "<b>2️⃣ Criar a Comunidade Hub + 8 Canais Comissionados:</b>",
        "No Telegram, crie os canais abaixo, adicione este Bot como <b>Administrador</b> (com permissão de postar, editar informações e fixar) e poste o comando <code>/vincular ...</code> dentro de cada canal — <b>o Bot renomeia, coloca a bio bonita, fixa as boas-vindas e apaga o comando sozinho!</b>",
        "",
    ]
    for key, spec in CHANNEL_CATALOG.items():
        lines.append(f"• {spec['emoji']} <b>{html.escape(spec['short_name'])}</b> → poste <code>/vincular {key}</code>")

    lines.extend(
        [
            "",
            "<b>3️⃣ Criar Pasta Compartilhável (Comunidade em 1 clique):</b>",
            "• No Telegram: <i>Configurações → Pastas de Chat → Criar Nova Pasta</i> → adicione a Comunidade Hub e os 8 Canais → clique em <b>Compartilhar Pasta</b>.",
            "• Envie o link gerado aqui: <code>/pasta https://t.me/addlist/...</code>",
            "• O Bot atualiza automaticamente o botão no topo da Comunidade Hub!",
        ]
    )
    return "\n".join(lines)


async def execute_affiliate_link_autoconfig(raw_url: str, database: DatabaseManager = db) -> tuple[bool, str]:
    params = await extract_affiliate_params_from_url(raw_url)
    tool = params.get("ml_matt_tool")
    word = params.get("ml_matt_word", "")

    if not tool:
        return (
            False,
            "❌ <b>Não consegui encontrar <code>matt_tool</code> neste link.</b>\n"
            "Abra qualquer produto no Mercado Livre pela sua conta de Afiliado, clique em <b>Compartilhar</b> na Barra de Afiliados e envie o link gerado aqui, "
            "ou configure manualmente com:\n<code>/afiliado ml_matt_tool SEU_NUMERO</code>",
        )

    database.set_config("ml_matt_tool", tool)
    if word:
        database.set_config("ml_matt_word", word)

    sample = build_fallback_affiliate_url(
        "https://produto.mercadolivre.com.br/MLB-12345678-produto-teste-_JM",
        matt_tool=tool,
        matt_word=word or None,
    )
    return (
        True,
        "✅ <b>Afiliado Mercado Livre configurado com sucesso!</b>\n\n"
        f"• <b>matt_tool:</b> <code>{html.escape(tool)}</code>\n"
        f"• <b>matt_word:</b> <code>{html.escape(word or '(não definido)')}</code>\n"
        f"• <b>Exemplo de link monetizado:</b>\n<code>{html.escape(sample)}</code>\n\n"
        "🔒 <i>Trava de monetização 100% ativa: todas as ofertas publicadas usarão seu link de afiliado.</i>",
    )
