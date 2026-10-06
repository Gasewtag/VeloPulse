"""Tests for Telegram bot /service conversational maintenance wizard."""

import random
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.bot.handlers.service import (
    handle_bike_selected,
    handle_cancel_service,
    handle_component_selected,
    handle_cost_message,
    handle_notes_message,
    handle_service_command,
    handle_service_type_selected,
    handle_skip_cost_callback,
    handle_skip_notes_callback,
    parse_cost_input,
)
from velopulse.bot.states import ServiceStates
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType, MaintenanceType
from velopulse.db.models.maintenance import MaintenanceLog
from velopulse.db.models.user import User


def test_parse_cost_input() -> None:
    """Test cost string parsing with various currencies and formats."""
    assert parse_cost_input("25.50") == Decimal("25.50")
    assert parse_cost_input("25,50") == Decimal("25.50")
    assert parse_cost_input("0") == Decimal("0")
    assert parse_cost_input(" 15.00 ") == Decimal("15.00")
    assert parse_cost_input("$45.00") == Decimal("45.00")
    assert parse_cost_input("100€") == Decimal("100")
    assert parse_cost_input("500 ₽") == Decimal("500")
    assert parse_cost_input("invalid") is None
    assert parse_cost_input("-10") is None


@pytest.mark.asyncio
async def test_service_wizard_no_user(db_session: AsyncSession) -> None:
    """Verify /service command prompts unauthenticated users to set up profile."""
    chat_id = random.randint(10_000_000, 99_999_999)
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_service_command(msg, state)

    msg.answer.assert_called_once()
    assert "profile setup" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_service_wizard_no_bikes(db_session: AsyncSession) -> None:
    """Verify /service notifies user when no active bicycles are registered."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Primoz",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_service_command(msg, state)

    msg.answer.assert_called_once()
    assert "don't have any registered bicycles" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_service_wizard_complete_flow_clean_and_lube(db_session: AsyncSession) -> None:
    """Verify full step-by-step wizard flow for Clean & Lube maintenance action."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Tadej",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{chat_id}",
        name="Colnago V4Rs",
        bike_type=BikeType.ROAD,
        total_distance_m=650_000,  # 650 km
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Dura-Ace 12s",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("1500.00"),
        status=ComponentStatus.OPTIMAL,
    )
    db_session.add(comp)
    await db_session.flush()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    # Step 1: /service command
    msg_start = AsyncMock(spec=Message)
    msg_start.chat = Chat(id=chat_id, type="private")
    msg_start.answer = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_service_command(msg_start, state)

    current_state = await state.get_state()
    assert current_state == ServiceStates.selecting_bike.state
    msg_start.answer.assert_called_once()
    assert "Maintenance Service Logging" in msg_start.answer.call_args[0][0]

    # Step 2: Select Bike
    cb_bike = AsyncMock(spec=CallbackQuery)
    cb_bike.data = f"service:bike:{bike.id}"
    cb_bike.message = AsyncMock(spec=Message)
    cb_bike.message.chat = Chat(id=chat_id, type="private")
    cb_bike.message.edit_text = AsyncMock()
    cb_bike.answer = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_bike_selected(cb_bike, state)

    assert await state.get_state() == ServiceStates.selecting_component.state
    cb_bike.message.edit_text.assert_called_once()
    assert "Colnago V4Rs" in cb_bike.message.edit_text.call_args[0][0]

    # Step 3: Select Component
    cb_comp = AsyncMock(spec=CallbackQuery)
    cb_comp.data = f"service:comp:{comp.id}"
    cb_comp.message = AsyncMock(spec=Message)
    cb_comp.message.chat = Chat(id=chat_id, type="private")
    cb_comp.message.edit_text = AsyncMock()
    cb_comp.answer = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_component_selected(cb_comp, state)

    assert await state.get_state() == ServiceStates.selecting_service_type.state
    cb_comp.message.edit_text.assert_called_once()
    assert "Shimano Dura-Ace 12s" in cb_comp.message.edit_text.call_args[0][0]

    # Step 4: Select Service Type (Clean & Lube)
    cb_type = AsyncMock(spec=CallbackQuery)
    cb_type.data = "service:type:clean_and_lube"
    cb_type.message = AsyncMock(spec=Message)
    cb_type.message.chat = Chat(id=chat_id, type="private")
    cb_type.message.edit_text = AsyncMock()
    cb_type.answer = AsyncMock()

    await handle_service_type_selected(cb_type, state)
    assert await state.get_state() == ServiceStates.entering_notes.state
    cb_type.message.edit_text.assert_called_once()

    # Step 5: Enter technician notes
    msg_notes = AsyncMock(spec=Message)
    msg_notes.text = "Ultrasonic bath and hot wax application"
    msg_notes.answer = AsyncMock()

    await handle_notes_message(msg_notes, state)
    assert await state.get_state() == ServiceStates.entering_cost.state
    msg_notes.answer.assert_called_once()

    # Step 6: Enter Cost
    msg_cost = AsyncMock(spec=Message)
    msg_cost.text = "18.50"
    msg_cost.answer = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_cost_message(msg_cost, state)

    assert await state.get_state() is None  # FSM cleared
    msg_cost.answer.assert_called_once()
    summary = msg_cost.answer.call_args[0][0]
    assert "Maintenance Logged Successfully" in summary
    assert "18.50" in summary
    assert "Colnago V4Rs" in summary

    # Verify log in database
    log_stmt = select(MaintenanceLog).where(
        MaintenanceLog.user_id == user.id,
        MaintenanceLog.component_id == comp.id,
    )
    log = (await db_session.execute(log_stmt)).scalar_one_or_none()
    assert log is not None
    assert log.log_type == MaintenanceType.CLEAN_AND_LUBE
    assert log.cost == Decimal("18.50")
    assert log.description == "Ultrasonic bath and hot wax application"
    assert log.odometer_km == Decimal("650.00")


@pytest.mark.asyncio
async def test_service_wizard_replace_workflow(db_session: AsyncSession) -> None:
    """Verify service wizard with REPLACE action archives old component and provisions new."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Remco",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{chat_id}",
        name="Specialized Tarmac",
        bike_type=BikeType.ROAD,
        total_distance_m=1_000_000,
    )
    db_session.add(bike)
    await db_session.flush()

    old_comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.FRONT_TIRE,
        brand_model="Specialized Turbo Cotton",
        lifespan_wear_points=Decimal("4000.00"),
        current_wear_points=Decimal("4100.00"),
        status=ComponentStatus.REPLACE_RECOMMENDED,
    )
    db_session.add(old_comp)
    await db_session.flush()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    await state.set_state(ServiceStates.entering_cost)
    await state.update_data(
        user_id=str(user.id),
        bike_id=str(bike.id),
        bike_name=bike.name,
        component_id=str(old_comp.id),
        component_name=old_comp.brand_model,
        service_type=MaintenanceType.REPLACE.value,
        notes="Punctured beyond repair on gravel patch",
        language="en",
    )

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    msg_cost = AsyncMock(spec=Message)
    msg_cost.text = "75.00"
    msg_cost.answer = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_cost_message(msg_cost, state)

    assert await state.get_state() is None
    msg_cost.answer.assert_called_once()
    summary = msg_cost.answer.call_args[0][0]
    assert "Component Replaced & Reset" in summary
    assert "75.00" in summary

    # Verify old component is RETIRED
    await db_session.refresh(old_comp)
    assert old_comp.status == ComponentStatus.RETIRED
    assert old_comp.retired_at is not None

    # Verify new active component
    new_comp_stmt = select(Component).where(
        Component.bike_id == bike.id,
        Component.retired_at.is_(None),
    )
    new_comp = (await db_session.execute(new_comp_stmt)).scalar_one_or_none()
    assert new_comp is not None
    assert new_comp.current_wear_points == Decimal("0.00")
    assert new_comp.status == ComponentStatus.NEW


@pytest.mark.asyncio
async def test_service_wizard_skip_buttons_flow(db_session: AsyncSession) -> None:
    """Verify skip buttons for notes and cost allow 0/free and empty notes."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Wout",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{chat_id}",
        name="Cervelo Aspero",
        bike_type=BikeType.GRAVEL,
        total_distance_m=100_000,
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.BOTTOM_BRACKET,
        brand_model="CeramicSpeed T47",
        lifespan_wear_points=Decimal("10000.00"),
    )
    db_session.add(comp)
    await db_session.flush()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    await state.set_state(ServiceStates.entering_notes)
    await state.update_data(
        user_id=str(user.id),
        bike_id=str(bike.id),
        bike_name=bike.name,
        component_id=str(comp.id),
        component_name=comp.brand_model,
        service_type=MaintenanceType.INSPECT_TUNE.value,
        language="en",
    )

    # 1. Skip notes
    cb_skip_notes = AsyncMock(spec=CallbackQuery)
    cb_skip_notes.message = AsyncMock(spec=Message)
    cb_skip_notes.message.edit_text = AsyncMock()
    cb_skip_notes.answer = AsyncMock()

    await handle_skip_notes_callback(cb_skip_notes, state)
    assert await state.get_state() == ServiceStates.entering_cost.state
    cb_skip_notes.message.edit_text.assert_called_once()

    # 2. Skip cost (Free / 0.00)
    cb_skip_cost = AsyncMock(spec=CallbackQuery)
    cb_skip_cost.message = AsyncMock(spec=Message)
    cb_skip_cost.message.answer = AsyncMock()
    cb_skip_cost.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_skip_cost_callback(cb_skip_cost, state)

    assert await state.get_state() is None
    cb_skip_cost.message.answer.assert_called_once()
    summary = cb_skip_cost.message.answer.call_args[0][0]
    assert "0.00" in summary


@pytest.mark.asyncio
async def test_service_wizard_invalid_cost_validation() -> None:
    """Verify non-numeric cost input triggers error and keeps state."""
    chat_id = random.randint(10_000_000, 99_999_999)
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    await state.set_state(ServiceStates.entering_cost)
    await state.update_data(language="en")

    msg = AsyncMock(spec=Message)
    msg.text = "abc_invalid_amount"
    msg.answer = AsyncMock()

    await handle_cost_message(msg, state)

    assert await state.get_state() == ServiceStates.entering_cost.state
    msg.answer.assert_called_once()
    assert "Invalid amount" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_service_wizard_cancellation(db_session: AsyncSession) -> None:
    """Verify /cancel command and cancel button clears state and reports cancellation."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Filippo",
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    await state.set_state(ServiceStates.entering_notes)

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__ = AsyncMock()

    # Via Message (/cancel)
    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_cancel_service(msg, state)

    assert await state.get_state() is None
    msg.answer.assert_called_once()
    assert "cancelled" in msg.answer.call_args[0][0].lower()

    # Via CallbackQuery (service:cancel)
    await state.set_state(ServiceStates.selecting_bike)
    cb = AsyncMock(spec=CallbackQuery)
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    with patch("velopulse.bot.handlers.service.get_session_context", mock_ctx):
        await handle_cancel_service(cb, state)

    assert await state.get_state() is None
    cb.message.edit_text.assert_called_once()
    assert "cancelled" in cb.message.edit_text.call_args[0][0].lower()
