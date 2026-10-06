import contextlib
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velopulse.bot.i18n import t
from velopulse.bot.keyboards import get_profile_menu_keyboard, get_strava_keyboard
from velopulse.bot.utils.helpers import get_user_by_chat_id, get_user_language
from velopulse.core.config import get_settings
from velopulse.db.session import get_session_context

logger = logging.getLogger("velopulse.bot.profile")
router = Router(name="profile")
settings = get_settings()


@router.callback_query(F.data == "open:strava")
async def handle_open_strava(query: CallbackQuery, state: FSMContext) -> None:
    """Display Strava integration status and authorization link."""
    if not isinstance(query.message, Message):
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

        if user and user.strava_athlete_id:
            status_text = t("strava_connected", lang, athlete_id=user.strava_athlete_id)
        else:
            status_text = t("strava_not_connected", lang)

    auth_url = settings.STRAVA_WEBHOOK_CALLBACK_URL.replace(
        "/webhooks/strava", "/auth/strava/authorize"
    )

    body = t(
        "strava_title",
        lang,
        status_text=status_text,
        auth_url=auth_url,
    )

    try:
        await query.message.edit_text(
            body,
            reply_markup=get_strava_keyboard(lang),
        )
    except Exception:
        await query.message.answer(
            body,
            reply_markup=get_strava_keyboard(lang),
        )
    await query.answer()


@router.callback_query(F.data == "chat:clean")
async def handle_clean_chat(query: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Clean recent messages in chat and present a fresh profile menu."""
    if not isinstance(query.message, Message):
        return

    await state.clear()
    chat_id = query.message.chat.id
    current_msg_id = query.message.message_id

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

    with contextlib.suppress(Exception):
        await query.answer("🧹 " + t("chat_cleaned", lang))

    # Delete previous up to 60 messages
    for msg_id in range(current_msg_id, max(1, current_msg_id - 60), -1):
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)

    menu_text = t("profile_menu_title", lang)
    await bot.send_message(
        chat_id=chat_id,
        text=menu_text,
        reply_markup=get_profile_menu_keyboard(lang),
    )
