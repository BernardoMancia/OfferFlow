from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional, Tuple

from telegram import Bot, Chat, ChatMember, ChatPermissions, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from config import OFFICIAL_TOPICS
from database.db import DatabaseManager, db
from database.logger import get_logger

logger = get_logger("telegram.setup_topics")
_SETUP_LOCK = asyncio.Lock()
_ADMIN_CACHE: Dict[Tuple[int, int], Tuple[bool, float]] = {}
_ADMIN_CACHE_TTL = 60.0


async def sync_group_metadata(
    bot: Bot, chat_id: int, database: DatabaseManager = db
) -> Dict[str, str]:
    info = {
        "group_title": database.get_config("group_title", "") or "",
        "group_username": database.get_config("group_username", "") or "",
        "group_url": database.get_config("group_url", "") or "",
    }
    try:
        chat = await bot.get_chat(chat_id)
        if chat.title:
            info["group_title"] = chat.title
            database.set_config("group_title", chat.title)
        if chat.username:
            info["group_username"] = chat.username
            info["group_url"] = f"https://t.me/{chat.username}"
            database.set_config("group_username", chat.username)
            database.set_config("group_url", info["group_url"])
        else:
            invite = chat.invite_link
            if not invite:
                try:
                    invite = await bot.export_chat_invite_link(chat_id)
                except TelegramError:
                    invite = ""
            if invite:
                info["group_url"] = invite
                database.set_config("group_url", invite)
    except TelegramError as exc:
        logger.debug(f"Não foi possível sincronizar metadados do grupo {chat_id}: {exc}")

    return info


async def lock_group_for_non_admins(bot: Bot, chat_id: int) -> bool:
    await sync_group_metadata(bot, chat_id, database=db)
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions.no_permissions(),
        )
        logger.info(
            f"Permissões do grupo {chat_id} blindadas: apenas Administradores podem enviar mensagens nos tópicos."
        )
        return True
    except TelegramError as exc:
        logger.warning(
            f"Não foi possível aplicar set_chat_permissions no grupo {chat_id} "
            f"(verifique a permissão 'Banir usuários / Restringir membros'): {exc}"
        )
        return False


async def is_user_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    now = time.monotonic()
    cache_key = (chat_id, user_id)
    cached = _ADMIN_CACHE.get(cache_key)
    if cached and (now - cached[1]) < _ADMIN_CACHE_TTL:
        return cached[0]

    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        is_adm = member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
        _ADMIN_CACHE[cache_key] = (is_adm, now)
        return is_adm
    except TelegramError:
        return False


async def ensure_forum_topics(
    bot: Bot,
    chat_id: int,
    database: DatabaseManager = db,
    force_recreate: bool = False,
) -> Dict[str, int]:
    async with _SETUP_LOCK:
        old_chat_id = database.get_chat_id()
        if old_chat_id and old_chat_id != chat_id:
            logger.info(
                f"Mudança de grupo detectada ({old_chat_id} -> {chat_id}). Resetando tópicos antigos."
            )
            database.reset_topics()

        database.set_chat_id(chat_id)
        await lock_group_for_non_admins(bot, chat_id)

        if force_recreate:
            database.reset_topics()

        pending = database.get_pending_topics()
        created_map: Dict[str, int] = {}

        if not pending:
            logger.info(f"Todos os 6 tópicos já estão configurados para o grupo {chat_id}.")
            return {
                t["topic_key"]: int(t["thread_id"])
                for t in database.get_all_topics()
                if t["thread_id"] is not None
            }

        logger.info(
            f"Iniciando criação automática de {len(pending)} tópico(s) no grupo {chat_id}..."
        )

        for item in pending:
            topic_key = item["topic_key"]
            topic_name = item["topic_name"]
            if database.get_topic_thread_id(topic_key) is not None:
                continue
            try:
                forum_topic = await bot.create_forum_topic(
                    chat_id=chat_id,
                    name=topic_name,
                )
                thread_id = int(forum_topic.message_thread_id)
                database.set_topic_thread_id(topic_key, thread_id)
                created_map[topic_key] = thread_id
                logger.info(
                    f"Tópico criado com sucesso: [{topic_key}] '{topic_name}' -> thread_id={thread_id}"
                )
                await asyncio.sleep(0.5)
            except TelegramError as exc:
                logger.error(
                    f"Erro ao criar tópico [{topic_key}] '{topic_name}' no grupo {chat_id}: {exc}"
                )

        return {
            t["topic_key"]: int(t["thread_id"])
            for t in database.get_all_topics()
            if t["thread_id"] is not None
        }


async def recreate_single_topic(
    bot: Bot,
    chat_id: int,
    topic_key: str,
    database: DatabaseManager = db,
) -> Optional[int]:
    topic_name = OFFICIAL_TOPICS.get(topic_key)
    if not topic_name:
        return None
    try:
        forum_topic = await bot.create_forum_topic(chat_id=chat_id, name=topic_name)
        thread_id = int(forum_topic.message_thread_id)
        database.set_topic_thread_id(topic_key, thread_id)
        logger.info(
            f"Tópico recriado automaticamente: [{topic_key}] '{topic_name}' -> thread_id={thread_id}"
        )
        return thread_id
    except TelegramError as exc:
        logger.error(f"Falha ao recriar tópico [{topic_key}]: {exc}")
        return None


async def handle_my_chat_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    my_chat_member = update.my_chat_member
    if not my_chat_member:
        return

    chat: Chat = my_chat_member.chat
    new_member: ChatMember = my_chat_member.new_chat_member

    if chat.type != ChatType.SUPERGROUP:
        return

    if new_member.status != ChatMember.ADMINISTRATOR:
        logger.info(
            f"Bot adicionado ao grupo {chat.id} ({chat.title}), mas status='{new_member.status}' (aguardando Admin)."
        )
        return

    if not getattr(chat, "is_forum", False):
        logger.warning(
            f"Bot virou Admin no supergrupo {chat.id} ({chat.title}), mas Tópicos (is_forum) está desativado."
        )
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "⚠️ <b>Atenção:</b> Eu fui promovido a Administrador, mas a opção "
                    "<b>Tópicos (Topics)</b> ainda não está ativada neste grupo.\n\n"
                    "👉 Ative os <b>Tópicos</b> nas configurações do grupo e envie "
                    "<code>/configurar</code> para que eu crie as 6 categorias automaticamente!"
                ),
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass
        return

    can_manage_topics = getattr(new_member, "can_manage_topics", True)
    if can_manage_topics is False:
        logger.warning(
            f"Bot virou Admin no grupo {chat.id}, mas sem a permissão 'Gerenciar Tópicos' (can_manage_topics)."
        )
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "⚠️ <b>Permissão Pendente:</b> Marque a permissão <b>Gerenciar Tópicos</b> "
                    "nas configurações de Administrador do Bot e envie <code>/configurar</code>."
                ),
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass
        return

    logger.info(
        f"Auto-Setup acionado: Bot promovido a Admin no supergrupo com Fórum {chat.id} ({chat.title})."
    )
    await ensure_forum_topics(context.bot, chat.id)
    summary_lines = [
        "✅ <b>Auto-Configuração Concluída com Sucesso!</b>",
        f"🆔 <b>Grupo (chat_id):</b> <code>{chat.id}</code>",
        "",
        "📂 <b>Tópicos Configurados:</b>",
    ]
    for t in db.get_all_topics():
        tid = t["thread_id"]
        status_str = f"<code>thread_id={tid}</code>" if tid else "❌ Pendente"
        summary_lines.append(f"• {t['topic_name']} — {status_str}")

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="\n".join(summary_lines),
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as exc:
        logger.warning(f"Não foi possível enviar resumo no tópico geral: {exc}")


async def cmd_configurar(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if not chat or not message:
        return

    if chat.type != ChatType.SUPERGROUP or not getattr(chat, "is_forum", False):
        await message.reply_text(
            "⚠️ Este comando deve ser executado dentro de um <b>Supergrupo com a opção Tópicos (Topics) ativada</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    is_anon_admin = bool(message.sender_chat and message.sender_chat.id == chat.id)
    if not is_anon_admin and (not user or not await is_user_admin(context.bot, chat.id, user.id)):
        try:
            await message.delete()
        except TelegramError:
            pass
        return

    force = bool(context.args and context.args[0].lower() in ("reset", "forcar", "force"))
    await ensure_forum_topics(context.bot, chat.id, force_recreate=force)

    lines = [
        "✅ <b>Tópicos Verificados e Sincronizados!</b>",
        f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>",
        "🔒 <b>Modo Estrito Ativo:</b> Somente Administradores podem enviar mensagens nos tópicos.",
        "",
    ]
    for t in db.get_all_topics():
        tid = t["thread_id"]
        status_str = f"<code>#{tid}</code>" if tid else "❌ <i>Erro ao criar (verifique permissão Gerenciar Tópicos)</i>"
        lines.append(f"• {t['topic_name']} → {status_str}")

    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def enforce_admin_only_messages(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or chat.type != ChatType.SUPERGROUP:
        return

    if (
        message.forum_topic_created
        or message.forum_topic_edited
        or message.forum_topic_closed
        or message.forum_topic_reopened
        or message.general_forum_topic_hidden
        or message.general_forum_topic_unhidden
        or message.new_chat_members
        or message.left_chat_member
        or message.pinned_message
    ):
        return

    if user and user.id == context.bot.id:
        return
    if message.sender_chat and message.sender_chat.id == chat.id:
        return

    if user and await is_user_admin(context.bot, chat.id, user.id):
        return

    try:
        await message.delete()
        logger.info(
            f"Mensagem de não-admin (user_id={user.id if user else 'unknown'}) "
            f"apagada automaticamente no tópico thread_id={message.message_thread_id}."
        )
    except TelegramError as exc:
        logger.warning(f"Falha ao apagar mensagem de não-admin: {exc}")

    await lock_group_for_non_admins(context.bot, chat.id)


async def handle_first_group_activity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if _SETUP_LOCK.locked():
        return
    if update.effective_user and update.effective_user.is_bot:
        return

    chat = update.effective_chat
    if not chat or chat.type != ChatType.SUPERGROUP or not getattr(chat, "is_forum", False):
        return

    current_chat_id = db.get_chat_id()
    pending = db.get_pending_topics()
    if current_chat_id == chat.id and not pending:
        return

    try:
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if member.status == ChatMember.ADMINISTRATOR and getattr(member, "can_manage_topics", True):
            logger.info(
                f"Auto-Setup via atividade inicial no grupo {chat.id} ({chat.title}). Criando tópicos..."
            )
            await ensure_forum_topics(context.bot, chat.id)
    except TelegramError as exc:
        logger.debug(f"Verificação de admin em {chat.id}: {exc}")
