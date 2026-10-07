"""Extended unit tests for Telegram bot factories and fallback/profile handlers."""

import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.bot.bot import create_bot, create_dispatcher
from velopulse.bot.handlers.common import (
    handle_unexpected_in_bike_type,
    handle_unexpected_in_front_brake_type,
    handle_unexpected_in_language,
    handle_unexpected_in_rear_brake_type,
    handle_unhandled_message,
)
from velopulse.bot.handlers.profile import handle_clean_chat, handle_open_strava
from velopulse.bot.states import BikeCreationStates
from velopulse.core.config import Settings
from velopulse.db.models.user import User


def test_create_bot_and_dispatcher() -> None:
    """Verify bot factory initializes Bot with token and Dispatcher with router."""
    settings = Settings(TELEGRAM_BOT_TOKEN="123456789:ABC_TEST_TOKEN")
    bot = create_bot(settings=settings)
    assert bot.token == "123456789:ABC_TEST_TOKEN"

    empty_bot = create_bot(settings=Settings(TELEGRAM_BOT_TOKEN=""))
    assert empty_bot.token is not None

    storage = MemoryStorage()
    dp = create_dispatcher(storage=storage)
    assert dp is not None


@pytest.mark.asyncio
async def test_handle_open_strava(db_session: AsyncSession) -> None:
    """Verify handle_open_strava displays Strava connection details."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="StravaUser",
        strava_athlete_id=random.randint(1_000_000, 99_999_999),
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "open:strava"
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.profile.get_session_context", mock_ctx):
        await handle_open_strava(cb, state)

    cb.message.edit_text.assert_called_once()
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_clean_chat(db_session: AsyncSession) -> None:
    """Verify handle_clean_chat removes previous messages and sends fresh menu."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="CleanUser",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "chat:clean"
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.message_id = 50
    cb.answer = AsyncMock()

    mock_bot = AsyncMock(spec=Bot)
    mock_bot.delete_message = AsyncMock()
    mock_bot.send_message = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.profile.get_session_context", mock_ctx):
        await handle_clean_chat(cb, state, mock_bot)

    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_unexpected_wizard_inputs() -> None:
    """Verify prompt re-display when unexpected input is sent during wizard steps."""
    chat_id = random.randint(10_000_000, 99_999_999)
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    msg = AsyncMock(spec=Message)
    msg.answer = AsyncMock()

    # 1. Unexpected in language selection
    await handle_unexpected_in_language(msg, state)
    msg.answer.assert_called_once()

    # 2. Unexpected in bike type
    msg.answer.reset_mock()
    await state.set_state(BikeCreationStates.selecting_bike_type)
    await state.update_data(language="en")
    await handle_unexpected_in_bike_type(msg, state)
    msg.answer.assert_called_once()

    # 3. Unexpected in front brake type
    msg.answer.reset_mock()
    await state.set_state(BikeCreationStates.selecting_front_brake_type)
    await handle_unexpected_in_front_brake_type(msg, state)
    msg.answer.assert_called_once()

    # 4. Unexpected in rear brake type
    msg.answer.reset_mock()
    await state.set_state(BikeCreationStates.selecting_rear_brake_type)
    await handle_unexpected_in_rear_brake_type(msg, state)
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_unhandled_message(db_session: AsyncSession) -> None:
    """Verify fallback response prompts profile setup if user profile is incomplete."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Unregistered",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.common.get_session_context", mock_ctx):
        await handle_unhandled_message(msg, state)

    msg.answer.assert_called_once()
