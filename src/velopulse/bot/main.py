"""Standalone entrypoint runner for VeloPulse Telegram bot."""

import asyncio
import logging

from velopulse.bot.bot import create_bot, create_dispatcher
from velopulse.core.logging import setup_logging

logger = logging.getLogger("velopulse.bot.main")


async def main() -> None:
    """Launch the Telegram Bot in polling mode."""
    setup_logging()
    logger.info("Initializing VeloPulse Telegram Bot...")

    bot = create_bot()
    dp = create_dispatcher()

    try:
        # Delete any pending webhook updates to avoid conflicts in polling mode
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting Telegram long polling...")
        await dp.start_polling(bot)
    except Exception as exc:
        logger.error("Telegram bot runner crashed: %s", exc)
        raise
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
