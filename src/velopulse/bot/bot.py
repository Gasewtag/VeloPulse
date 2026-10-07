"""aiogram 3.x bot and dispatcher factories."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage

from velopulse.bot.handlers import main_router
from velopulse.core.config import Settings, get_settings

logger = logging.getLogger("velopulse.bot")


def create_bot(settings: Settings | None = None) -> Bot:
    """Create and configure an aiogram Bot instance."""
    s = settings or get_settings()
    if not s.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not set or empty in configuration")
    return Bot(
        token=s.TELEGRAM_BOT_TOKEN or "123456789:AABBCCDDEEFF_dummy_token_testing",
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(storage: BaseStorage | None = None) -> Dispatcher:
    """Create and configure an aiogram Dispatcher instance with all registered routers."""
    if storage is None:
        try:
            s = get_settings()
            storage = RedisStorage.from_url(s.REDIS_URL)
        except Exception as exc:
            logger.debug("Falling back to default memory storage: %s", exc)
            storage = None

    dp = Dispatcher(storage=storage) if storage is not None else Dispatcher()
    dp.include_router(main_router)
    return dp
