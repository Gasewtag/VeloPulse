"""Extended tests for Telegram bot bike management and wizard validation."""

import random
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.bot.handlers.bikes import (
    handle_bike_manage_menu,
    handle_cassette_text,
    handle_chain_lube_text,
    handle_chain_text,
    handle_delete_bike_confirm,
    handle_delete_bike_prompt,
    handle_list_bikes,
)
from velopulse.bot.states import BikeCreationStates
from velopulse.db.models.bike import Bike
from velopulse.db.models.enums import BikeType
from velopulse.db.models.user import User


@pytest.mark.asyncio
async def test_list_bikes_callback_and_message(db_session: AsyncSession) -> None:
    """Verify handle_list_bikes renders list via callback and message."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Rider",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g_list_{uuid.uuid4().hex[:8]}",
        name="Roubaix",
        bike_type=BikeType.ROAD,
    )
    db_session.add(bike)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.bikes.get_session_context", mock_ctx):
        # 1. Via CallbackQuery
        cb = AsyncMock(spec=CallbackQuery)
        cb.data = "open:bikes"
        cb.message = AsyncMock(spec=Message)
        cb.message.chat = Chat(id=chat_id, type="private")
        cb.message.edit_text = AsyncMock()
        cb.answer = AsyncMock()

        await handle_list_bikes(cb, state)
        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()

        # 2. Via Message
        msg = AsyncMock(spec=Message)
        msg.chat = Chat(id=chat_id, type="private")
        msg.answer = AsyncMock()
        await handle_list_bikes(msg, state)
        msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_wizard_text_mileage_inputs() -> None:
    """Verify mileage text parsing in bike creation wizard."""
    chat_id = random.randint(10_000_000, 99_999_999)
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    # Cassette text: invalid then valid
    await state.set_state(BikeCreationStates.entering_cassette_mileage)
    await state.update_data(language="en")

    msg_inv = AsyncMock(spec=Message)
    msg_inv.text = "invalid"
    msg_inv.answer = AsyncMock()
    await handle_cassette_text(msg_inv, state)
    msg_inv.answer.assert_called_once()

    msg_val = AsyncMock(spec=Message)
    msg_val.text = "1500"
    msg_val.answer = AsyncMock()
    await handle_cassette_text(msg_val, state)
    assert await state.get_state() == BikeCreationStates.entering_chain_mileage

    # Chain text: invalid then valid
    msg_inv.answer.reset_mock()
    msg_inv.text = "-10"
    await handle_chain_text(msg_inv, state)
    msg_inv.answer.assert_called_once()

    msg_val.answer.reset_mock()
    msg_val.text = "300"
    await handle_chain_text(msg_val, state)
    assert await state.get_state() == BikeCreationStates.entering_chain_lube_mileage

    # Chain lube text: invalid then valid
    msg_inv.answer.reset_mock()
    msg_inv.text = "xyz"
    await handle_chain_lube_text(msg_inv, state)
    msg_inv.answer.assert_called_once()

    msg_val.answer.reset_mock()
    msg_val.text = "50"
    await handle_chain_lube_text(msg_val, state)
    assert await state.get_state() == BikeCreationStates.entering_front_tire_mileage


@pytest.mark.asyncio
async def test_bike_manage_and_delete_flow(db_session: AsyncSession) -> None:
    """Verify bike manage cockpit, delete prompt, and deletion confirmation."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Rider",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g_del_{uuid.uuid4().hex[:8]}",
        name="Old Commuter",
        bike_type=BikeType.COMMUTER,
    )
    db_session.add(bike)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.bikes.get_session_context", mock_ctx):
        # 1. Manage Menu (invalid ID)
        cb_inv = AsyncMock(spec=CallbackQuery)
        cb_inv.data = "bike:manage:invalid-uuid"
        cb_inv.message = AsyncMock(spec=Message)
        cb_inv.answer = AsyncMock()
        await handle_bike_manage_menu(cb_inv, state)
        cb_inv.answer.assert_called_with("Invalid bike ID", show_alert=True)

        # 2. Manage Menu (valid ID)
        cb_man = AsyncMock(spec=CallbackQuery)
        cb_man.data = f"bike:manage:{bike.id}"
        cb_man.message = AsyncMock(spec=Message)
        cb_man.message.chat = Chat(id=chat_id, type="private")
        cb_man.message.edit_text = AsyncMock()
        cb_man.answer = AsyncMock()
        await handle_bike_manage_menu(cb_man, state)
        cb_man.message.edit_text.assert_called_once()

        # 3. Delete prompt
        cb_del = AsyncMock(spec=CallbackQuery)
        cb_del.data = f"bike:delete_prompt:{bike.id}"
        cb_del.message = AsyncMock(spec=Message)
        cb_del.message.chat = Chat(id=chat_id, type="private")
        cb_del.message.edit_text = AsyncMock()
        cb_del.answer = AsyncMock()
        await handle_delete_bike_prompt(cb_del, state)
        cb_del.message.edit_text.assert_called_once()

        # 4. Delete confirm
        cb_conf = AsyncMock(spec=CallbackQuery)
        cb_conf.data = f"bike:delete_confirm:{bike.id}"
        cb_conf.message = AsyncMock(spec=Message)
        cb_conf.message.chat = Chat(id=chat_id, type="private")
        cb_conf.message.edit_text = AsyncMock()
        cb_conf.answer = AsyncMock()
        await handle_delete_bike_confirm(cb_conf, state)
        cb_conf.answer.assert_any_call("Bike has been deleted.", show_alert=True)

    # Verify bike is deleted
    deleted_bike = (
        await db_session.execute(select(Bike).where(Bike.id == bike.id))
    ).scalar_one_or_none()
    assert deleted_bike is None
