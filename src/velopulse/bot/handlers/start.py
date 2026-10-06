"""Telegram bot start, language selection, and onboarding handlers."""

import logging
import uuid

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from velopulse.bot.i18n import t
from velopulse.bot.keyboards import (
    get_language_keyboard,
    get_profile_menu_keyboard,
    get_profile_prompt_keyboard,
)
from velopulse.bot.states import LanguageStates, ProfileStates
from velopulse.bot.utils.helpers import (
    get_or_create_user,
    get_user_by_chat_id,
    get_user_language,
)
from velopulse.db.models.user import User
from velopulse.db.session import get_session_context

logger = logging.getLogger("velopulse.bot.start")
router = Router(name="start")


@router.message(CommandStart(deep_link=True))
async def handle_start_deeplink(
    message: Message,
    command: CommandObject,
    state: FSMContext | None = None,
) -> None:
    """Handle deep-linked /start onboarding (e.g., /start <user_uuid> or /start <athlete_id>)."""
    payload = command.args
    chat_id = message.chat.id
    first_name = message.from_user.first_name if message.from_user else "Cyclist"
    last_name = message.from_user.last_name if message.from_user else None

    if not payload:
        await handle_start_plain(message, state)
        return

    logger.info("Received deep-link start with payload '%s' from chat %s", payload, chat_id)

    async with get_session_context() as session:
        user: User | None = None

        # 1. Try parsing payload as UUID
        try:
            target_uuid = uuid.UUID(payload)
            stmt = select(User).where(User.id == target_uuid)
            user = (await session.execute(stmt)).scalar_one_or_none()
        except ValueError:
            pass

        # 2. Try parsing payload as Strava athlete ID
        if not user and payload.isdigit():
            athlete_id = int(payload)
            stmt = select(User).where(User.strava_athlete_id == athlete_id)
            user = (await session.execute(stmt)).scalar_one_or_none()

        if user:
            user.telegram_chat_id = chat_id
            await session.commit()
            logger.info("Linked athlete %s to telegram chat %s", user.strava_athlete_id, chat_id)
        else:
            # Create user if not found
            user = await get_or_create_user(chat_id, first_name, last_name, session)

    # Immediately ask for language selection without greeting
    if state:
        await state.set_state(LanguageStates.selecting_language)
    await message.answer(
        t("select_language", "en"),
        reply_markup=get_language_keyboard(),
    )


@router.message(CommandStart())
async def handle_start_plain(message: Message, state: FSMContext | None = None) -> None:
    """Handle plain /start command.

    Spec requirement:
    When user sends /start, bot must NOT send a greeting.
    Immediately send language selection message:
    'Please select your language:'
    Buttons:
    - 🇬🇧 English
    - 🇷🇺 Russian
    """
    chat_id = message.chat.id
    first_name = message.from_user.first_name if message.from_user else "Cyclist"
    last_name = message.from_user.last_name if message.from_user else None

    async with get_session_context() as session:
        await get_or_create_user(chat_id, first_name, last_name, session)

    if state:
        await state.set_state(LanguageStates.selecting_language)
    await message.answer(
        t("select_language", "en"),
        reply_markup=get_language_keyboard(),
    )


@router.callback_query(F.data.startswith("set_lang:"))
async def handle_language_selection(query: CallbackQuery, state: FSMContext) -> None:
    """Handle language selection callback and greet user."""
    if not query.data or not isinstance(query.message, Message):
        return

    lang = query.data.split(":", 1)[1]
    if lang not in ("en", "ru"):
        lang = "en"

    chat_id = query.message.chat.id
    first_name = query.from_user.first_name if query.from_user else "Cyclist"

    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        if user:
            current_settings = dict(user.settings or {})
            current_settings["language"] = lang
            user.settings = current_settings
            await session.commit()

    await state.update_data(language=lang)

    # Greet user dynamically by first name
    greeting_text = t("greeting", lang, first_name=first_name)
    await query.message.edit_text(
        greeting_text,
        reply_markup=get_profile_prompt_keyboard(lang),
    )
    await query.answer()

    # Move to awaiting profile setup state
    await state.set_state(ProfileStates.awaiting_profile_setup)


@router.callback_query(F.data == "open:profile")
async def handle_open_profile(query: CallbackQuery, state: FSMContext) -> None:
    """Open Profile menu and mark profile setup as completed."""
    if not isinstance(query.message, Message):
        return

    chat_id = query.message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)
        if user:
            current_settings = dict(user.settings or {})
            current_settings["profile_setup_completed"] = True
            user.settings = current_settings
            await session.commit()

    # Clear awaiting profile setup state
    current_state = await state.get_state()
    if current_state == ProfileStates.awaiting_profile_setup.state:
        await state.clear()

    await state.update_data(language=lang)

    menu_text = t("profile_menu_title", lang)
    try:
        await query.message.edit_text(
            menu_text,
            reply_markup=get_profile_menu_keyboard(lang),
        )
    except Exception:
        await query.message.answer(
            menu_text,
            reply_markup=get_profile_menu_keyboard(lang),
        )
    await query.answer()


@router.message(ProfileStates.awaiting_profile_setup)
async def handle_uncompleted_profile_message(message: Message, state: FSMContext) -> None:
    """Block user from proceeding until profile setup is opened."""
    chat_id = message.chat.id
    async with get_session_context() as session:
        user = await get_user_by_chat_id(chat_id, session)
        lang = get_user_language(user)

    await message.answer(
        t("profile_not_setup", lang),
        reply_markup=get_profile_prompt_keyboard(lang),
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Explain bot commands and wear calculation mechanics."""
    chat = getattr(message, "chat", None)
    chat_id = chat.id if chat else None
    lang = "en"
    if chat_id:
        async with get_session_context() as session:
            user = await get_user_by_chat_id(chat_id, session)
            lang = get_user_language(user)

    if lang == "ru":
        text = (
            "🛠️ <b>Справка VeloPulse</b>\n\n"
            "<b>Доступные команды:</b>\n"
            "• /status — Сводка по оборудованию, требующему обслуживания\n"
            "• /bikes — Список зарегистрированных велосипедов\n"
            "• /components — Детальный износ компонентов\n"
            "• /help — Инструкция и справка\n\n"
            "<b>Как работает расчёт износа (Wear Points):</b>\n"
            "• <b>1.0 WP</b> = 1.0 км в идеальных условиях (сухой чистый асфальт).\n"
            "• <b>Погодный множитель:</b> Дождь, мокрая дорога и песок ускоряют износ цепи и колодок до <b>3.5x</b>.\n"
            "• <b>Фактор набора высоты:</b> Подъёмы и крутящий момент увеличивают растяжение цепи."
        )
    else:
        text = (
            "🛠️ <b>VeloPulse Assistant Help</b>\n\n"
            "<b>Available Commands:</b>\n"
            "• /status — Cockpit report showing components requiring service\n"
            "• /bikes — List all registered bicycles\n"
            "• /components — Detailed wear breakdown by part\n"
            "• /help — Explain commands & wear mechanics\n\n"
            "<b>How Wear Points (WP) Work:</b>\n"
            "• <b>1.0 WP</b> = 1.0 km under ideal conditions (clean, dry flat asphalt).\n"
            "• <b>Weather Multiplier:</b> Wet roads, rain, and grit multiply drivetrain and brake pad wear up to <b>3.5x</b>.\n"
            "• <b>Climbing Factor:</b> High torque ascents accelerate chain elongation and cog wear."
        )

    await message.answer(text)
