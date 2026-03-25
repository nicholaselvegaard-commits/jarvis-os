"""
NEXUS — Entry point.

Starts the Telegram bot (Jordan's interface) and APScheduler.
Replaces both Jordan's run.py and NEXUS's standalone bot starters.

Usage:
  python main.py

Deploy:
  bash deploy/deploy.sh
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Ensure nexus/ is importable
sys.path.insert(0, str(Path(__file__).parent))

BASE_DIR = Path(__file__).parent
(BASE_DIR / "memory").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "memory" / "nexus.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("NEXUS starting — Jordan + NEXUS merged agent")
    logger.info("=" * 60)

    import anthropic as _anthropic
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from telegram.ext import Application
    from interfaces.telegram_bot import (
        build_app,
        _startup_health_check,
        check_follow_ups,
    )
    from services.scheduler_service import register_jobs

    scheduler = AsyncIOScheduler()

    async def post_init(application: Application) -> None:
        """Run on startup: health check + start scheduler."""
        await _startup_health_check(application)
        register_jobs(scheduler, application=application)
        scheduler.start()
        logger.info(f"Scheduler started — {len(scheduler.get_jobs())} jobs active.")

    # Build app with our combined post_init
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    app = Application.builder().token(token).post_init(post_init).build()

    # Register all handlers from interfaces/telegram_bot.py
    from interfaces.telegram_bot import (
        cmd_start, cmd_ny, cmd_pending, cmd_ring, cmd_voicemode,
        cmd_search, cmd_url, cmd_github, cmd_model,
        cmd_goals, cmd_reflect, cmd_replies, cmd_memory, cmd_browse, cmd_todo,
        handle_message, handle_voice, handle_callback,
    )
    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters

    # Jordan's original commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ny",        cmd_ny))
    app.add_handler(CommandHandler("pending",   cmd_pending))
    app.add_handler(CommandHandler("ring",      cmd_ring))
    app.add_handler(CommandHandler("voicemode", cmd_voicemode))
    app.add_handler(CommandHandler("search",    cmd_search))
    app.add_handler(CommandHandler("url",       cmd_url))
    app.add_handler(CommandHandler("github",    cmd_github))
    app.add_handler(CommandHandler("model",     cmd_model))

    # NEXUS commands
    app.add_handler(CommandHandler("goals",   cmd_goals))
    app.add_handler(CommandHandler("reflect", cmd_reflect))
    app.add_handler(CommandHandler("replies", cmd_replies))
    app.add_handler(CommandHandler("memory",  cmd_memory))
    app.add_handler(CommandHandler("browse",  cmd_browse))
    app.add_handler(CommandHandler("todo",    cmd_todo))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Starting Telegram bot (polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
