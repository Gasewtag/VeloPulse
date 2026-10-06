"""Telegram bot command, callback, and FSM routers."""

from aiogram import Router

from velopulse.bot.handlers.bikes import router as bikes_router
from velopulse.bot.handlers.callbacks import router as callbacks_router
from velopulse.bot.handlers.common import router as common_router
from velopulse.bot.handlers.profile import router as profile_router
from velopulse.bot.handlers.settings import router as settings_router
from velopulse.bot.handlers.start import router as start_router
from velopulse.bot.handlers.status import router as status_router
from velopulse.bot.handlers.trips import router as trips_router

main_router = Router(name="main_router")
main_router.include_router(start_router)
main_router.include_router(profile_router)
main_router.include_router(bikes_router)
main_router.include_router(trips_router)
main_router.include_router(settings_router)
main_router.include_router(status_router)
main_router.include_router(callbacks_router)
main_router.include_router(common_router)

__all__ = [
    "bikes_router",
    "callbacks_router",
    "common_router",
    "main_router",
    "profile_router",
    "settings_router",
    "start_router",
    "status_router",
    "trips_router",
]
