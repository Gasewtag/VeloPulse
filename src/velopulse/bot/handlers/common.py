"""Fallback and generic input handlers for Telegram bot."""

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from velopulse.bot.i18n import t
from velopulse.bot.keyboards import (
    get_bike_type_keyboard,
    get_brake_type_keyboard,
    get_language_keyboard,
    get_profile_prompt_keyboard,
)
from velopulse.bot.states import (
    BikeCreationStates,
    LanguageStates,
)
from velopulse.bot.utils.helpers import (
    get_user_by_chat_id,
    get_user_language,
    is_profile_completed,
)
from velopulse.db.session import get_session_context

logger = logging.getLogger("velopulse.bot.common")
router = Router(name="common")


@router.message(LanguageStates.selecting_language)
async def handle_unexpected_in_language(message: Message, state: FSMContext) -> None:
    """Handle unexpected text when language selection button is expected."""
    await message.answer(
        t("select_language", "en"),
        reply_markup=get_language_keyboard(),
    )


@router.message(BikeCreationStates.selecting_bike_type)
async def handle_unexpected_in_bike_type(message: Message, state: FSMContext) -> None:
    """Handle unexpected text when bike type button is expected."""
    data = await state.get_data()
    lang = data.get("language", "en")
    await message.answer(
        t("step_bike_type", lang),
        reply_markup=get_bike_type_keyboard(lang),
    )


@router.message(BikeCreationStates.selecting_front_brake_type)
async def handle_unexpected_in_front_brake_type(message: Message, state: FSMContext) -> None:
    """Handle unexpected text when front brake type button is expected."""
    data = await state.get_data()
    lang = data.get("language", "en")
    await message.answer(
        t("step_front_brake_type", lang),
        reply_markup=get_brake_type_keyboard(lang),
    )


@router.message(BikeCreationStates.selecting_rear_brake_type)
async def handle_unexpected_in_rear_brake_type(message: Message, state: FSMContext) -> None:
    """Handle unexpected text when rear brake type button is expected."""
    data = await state.get_data()
    lang = data.get("language", "en")
    await message.answer(
        t("step_rear_brake_type", lang),
        reply_markup=get_brake_type_keyboard(lang),
    )


@router.message()
async def handle_unhandled_message(message: Message, state: FSMContext) -> None:
    """Handle free-form messages outside active wizards.

    Requirement:
    If profile is not completed, prompt profile setup:
    'Your profile is not set up yet. Please complete the profile setup to continue.' [ 👤 Profile ]
    """
    chat_id = message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        if not user or not is_profile_completed(user):
            await message.answer(
                t("profile_not_setup", lang),
                reply_markup=get_profile_prompt_keyboard(lang),
            )
            return

    await message.answer(t("unexpected_action", lang))
