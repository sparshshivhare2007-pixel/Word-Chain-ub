import asyncio
import signal
import sys
from telegram.ext import Application
from config import Config
from utils.logger import logger
from handlers.bot_handlers import register_bot_handlers
from userbot_manager import UserBotManager


async def graceful_shutdown(sig, application: Application):
    """Gracefully shutdown bot and sessions"""
    logger.info(f"Received exit signal {sig.name}...")

    manager = UserBotManager()

    tasks = []
    for key in list(manager.sessions.keys()):
        try:
            user_id, session_name = key.split("_", 1)
            tasks.append(
                manager.disconnect_session(int(user_id), session_name)
            )
        except Exception:
            continue

    if tasks:
        logger.info(f"Disconnecting {len(tasks)} active sessions...")
        await asyncio.gather(*tasks, return_exceptions=True)

    await application.stop()
    await application.shutdown()

    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Build application
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Register handlers
    register_bot_handlers(application)

    # Background cleanup task
    manager = UserBotManager()

    async def post_init(app: Application):
        asyncio.create_task(manager.cleanup_stale_sessions())

        logger.info("🚀 Wordle Bot started successfully")
        logger.info(f"Force join: {Config.FORCE_JOIN_CHAT or 'disabled'}")
        logger.info(
            f"Anti-ban delay: {Config.MIN_DELAY}-{Config.MAX_DELAY}s"
        )

    application.post_init = post_init

    # Graceful shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(
                graceful_shutdown(s, application)
            ),
        )

    # Start polling
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
