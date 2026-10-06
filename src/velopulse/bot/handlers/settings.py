"""Telegram bot handlers for settings and account management."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velopulse.bot.i18n import t
from velopulse.bot.keyboards import (
    get_delete_account_confirm_keyboard,
    get_settings_keyboard,
    get_settings_language_keyboard,
)
from velopulse.bot.utils.helpers import get_user_by_chat_id, get_user_language
from velopulse.db.session import get_session_context

logger = logging.getLogger("velopulse.bot.settings")
router = Router(name="settings")


@router.callback_query(F.data == "open:settings")
async def handle_open_settings(query: CallbackQuery, state: FSMContext) -> None:
    """Display user settings menu."""
    if not isinstance(query.message, Message):
        return

    await state.clear()
    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

    title = t("settings_title", lang)
    kb = get_settings_keyboard(lang)

    try:
        await query.message.edit_text(title, reply_markup=kb)
    except Exception:
        await query.message.answer(title, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "settings:language")
async def handle_open_settings_language(query: CallbackQuery, state: FSMContext) -> None:
    """Display language selection menu in settings."""
    if not isinstance(query.message, Message):
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

    msg_text = t("select_language", lang)
    kb = get_settings_language_keyboard(lang)

    try:
        await query.message.edit_text(msg_text, reply_markup=kb)
    except Exception:
        await query.message.answer(msg_text, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("settings:set_lang:"))
async def handle_settings_set_language(query: CallbackQuery, state: FSMContext) -> None:
    """Switch user language from settings and return to settings menu in the chosen language."""
    if not query.data or not isinstance(query.message, Message):
        return

    lang = query.data.split(":", 2)[2]
    if lang not in ("en", "ru"):
        lang = "en"

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        if user:
            current_settings = dict(user.settings or {})
            current_settings["language"] = lang
            user.settings = current_settings
            await session.commit()

    await state.update_data(language=lang)

    title = t("settings_title", lang)
    kb = get_settings_keyboard(lang)

    try:
        await query.message.edit_text(title, reply_markup=kb)
    except Exception:
        await query.message.answer(title, reply_markup=kb)
    await query.answer(t("lang_changed", lang))


@router.message(Command("language"))
async def handle_language_command(message: Message, state: FSMContext) -> None:
    """Allow user to switch language at any time via /language command."""
    chat_id = message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

    await message.answer(
        t("select_language", lang),
        reply_markup=get_settings_language_keyboard(lang),
    )


@router.callback_query(F.data == "settings:delete_account_prompt")
async def handle_delete_account_prompt(query: CallbackQuery, state: FSMContext) -> None:
    """Show account deletion confirmation prompt."""
    if not isinstance(query.message, Message):
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

    msg_text = t("delete_account_prompt", lang)
    kb = get_delete_account_confirm_keyboard(lang)

    await query.message.edit_text(msg_text, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "settings:delete_account_confirm")
async def handle_delete_account_confirm(query: CallbackQuery, state: FSMContext) -> None:
    """Permanently delete user profile, bikes, and telemetry, and send farewell message."""
    if not isinstance(query.message, Message):
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        if user:
            logger.info(
                "Permanently deleting account for telegram chat %s (user %s)", chat_id, user.id
            )
            await session.delete(user)
            await session.commit()

    await state.clear()

    farewell = t("account_deleted_farewell", lang)
    await query.message.edit_text(farewell, reply_markup=None)
    await query.answer()
