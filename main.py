from __future__ import annotations

import argparse
import asyncio
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import settings
from core.diagnostic import run_local_diagnostic
from core.pipeline import ingest_scraped_offers
from core.scheduler import (
    job_scrape_aggregators,
    job_scrape_ml_categories,
    job_scrape_ml_offers,
    post_init,
)
from database.logger import get_logger
from telegram_bot.admin_handlers import (
    _build_admin_panel_view,
    _check_command_admin,
    cmd_afiliado,
    cmd_canais,
    cmd_configurar_afiliado,
    cmd_cookie,
    cmd_fila,
    cmd_forcar_busca,
    cmd_guia_configuracao,
    cmd_limpar_fila,
    cmd_painel,
    cmd_pasta,
    cmd_pausar,
    cmd_postar,
    cmd_relatorio,
    cmd_resumo,
    cmd_retomar,
    cmd_status,
    cmd_testar_oferta,
    cmd_vincular,
)
from telegram_bot.callbacks import (
    _build_draft_preview_keyboard,
    handle_admin_callback,
    handle_private_message_guard,
)
from telegram_bot.channel_manager import handle_channel_post_commands
from telegram_bot.member_handlers import (
    cmd_alerta,
    cmd_historico,
    cmd_meus_alertas,
    cmd_remover_alerta,
    cmd_start,
)
from telegram_bot.setup_topics import (
    cmd_configurar,
    enforce_admin_only_messages,
    handle_first_group_activity,
    handle_my_chat_member,
)

logger = get_logger("main")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OfferFlow v2.0 — 100% Mercado Livre Affiliate Multi-Channel Telegram Ecosystem"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Executa autodiagnóstico local dos módulos sem conectar à API do Telegram.",
    )
    args = parser.parse_args()

    if args.check:
        sys.exit(asyncio.run(run_local_diagnostic()))

    if not settings.has_valid_telegram_token:
        logger.error(
            "TELEGRAM_BOT_TOKEN não configurado no arquivo .env! "
            "Abra o arquivo .env, preencha seu token do @BotFather e execute novamente. "
            "Para testar os módulos sem token, use: python main.py --check"
        )
        sys.exit(1)

    logger.info("Iniciando OfferFlow v2.0 (100% Mercado Livre Afiliados • Multi-Canal + Comunidade Hub)...")
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(
        MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post_commands),
        group=-2,
    )

    app.add_handler(
        MessageHandler(filters.ChatType.SUPERGROUP, enforce_admin_only_messages),
        group=-1,
    )

    app.add_handler(
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    app.add_handler(CommandHandler(["start", "ajuda", "help"], cmd_start))
    app.add_handler(CommandHandler(["alerta", "alert"], cmd_alerta))
    app.add_handler(CommandHandler(["meus_alertas", "alertas"], cmd_meus_alertas))
    app.add_handler(CommandHandler(["remover_alerta", "del_alerta"], cmd_remover_alerta))
    app.add_handler(CommandHandler(["historico", "grafico", "chart"], cmd_historico))

    app.add_handler(CommandHandler(["guia_configuracao", "guia", "setup"], cmd_guia_configuracao))
    app.add_handler(CommandHandler(["configurar_afiliado", "vincular_afiliado"], cmd_configurar_afiliado))
    app.add_handler(CommandHandler(["canais", "channels"], cmd_canais))
    app.add_handler(CommandHandler(["vincular", "bind"], cmd_vincular))
    app.add_handler(CommandHandler(["pasta", "folder"], cmd_pasta))

    app.add_handler(CommandHandler(["configurar", "setup_topicos"], cmd_configurar))
    app.add_handler(CommandHandler(["painel", "admin"], cmd_painel))
    app.add_handler(CommandHandler(["status", "info"], cmd_status))
    app.add_handler(CommandHandler(["relatorio", "report"], cmd_relatorio))
    app.add_handler(CommandHandler(["cookie", "set_cookie"], cmd_cookie))
    app.add_handler(CommandHandler(["afiliado", "afiliados"], cmd_afiliado))
    app.add_handler(CommandHandler(["fila", "queue"], cmd_fila))
    app.add_handler(CommandHandler(["limpar_fila", "clear_queue"], cmd_limpar_fila))
    app.add_handler(CommandHandler(["pausar", "pause"], cmd_pausar))
    app.add_handler(CommandHandler(["retomar", "resume"], cmd_retomar))
    app.add_handler(CommandHandler(["postar", "post"], cmd_postar))
    app.add_handler(CommandHandler(["resumo", "top5"], cmd_resumo))
    app.add_handler(CommandHandler(["testar_oferta", "teste"], cmd_testar_oferta))
    app.add_handler(CommandHandler(["forcar_busca", "buscar"], cmd_forcar_busca))
    app.add_handler(CallbackQueryHandler(handle_admin_callback))

    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private_message_guard),
        group=0,
    )

    app.add_handler(
        MessageHandler(filters.ChatType.SUPERGROUP, handle_first_group_activity),
        group=1,
    )

    logger.info("OfferFlow v2.0 em execução (Polling ativo). Aguardando eventos no Telegram...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


__all__ = [
    "_build_admin_panel_view",
    "_build_draft_preview_keyboard",
    "_check_command_admin",
    "ingest_scraped_offers",
    "job_scrape_aggregators",
    "job_scrape_ml_categories",
    "job_scrape_ml_offers",
    "main",
    "post_init",
    "run_local_diagnostic",
]

if __name__ == "__main__":
    main()
