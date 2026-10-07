"""Unit and integration tests for Telegram bot manual trip logging and wear calculation."""

import random
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.bot.handlers.trips import (
    handle_start_new_trip,
    handle_trip_bike_selected,
    handle_trip_distance_entered,
    handle_trip_elevation_preset,
    handle_trip_elevation_text,
)
from velopulse.bot.states import TripStates
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType
from velopulse.db.models.user import User


@pytest.mark.asyncio
async def test_trip_start_no_user(db_session: AsyncSession) -> None:
    """Verify handle_start_new_trip exits gracefully when user does not exist."""
    chat_id = random.randint(10_000_000, 99_999_999)
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    msg = AsyncMock(spec=Message)
    msg.chat = Chat(id=chat_id, type="private")
    msg.answer = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.trips.get_session_context", mock_ctx):
        await handle_start_new_trip(msg, state)

    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_trip_start_no_bikes(db_session: AsyncSession) -> None:
    """Verify handle_start_new_trip prompts to create a bike when none exist."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="TestRider",
        strava_athlete_id=random.randint(100_000, 999_999),
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

    with patch("velopulse.bot.handlers.trips.get_session_context", mock_ctx):
        await handle_start_new_trip(msg, state)

    msg.answer.assert_called_once()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_trip_full_workflow(db_session: AsyncSession) -> None:
    """Verify complete trip recording workflow with distance, elevation, and wear calculation."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="SpeedyRider",
        strava_athlete_id=random.randint(100_000, 999_999),
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g_trip_{uuid.uuid4().hex[:8]}",
        name="Tarmac SL7",
        bike_type=BikeType.ROAD,
        total_distance_m=100_000,
        is_active=True,
    )
    db_session.add(bike)
    await db_session.flush()

    chain = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Ultegra 12s",
        current_wear_points=Decimal("100.00"),
        lifespan_wear_points=Decimal("2000.00"),
        status=ComponentStatus.OPTIMAL,
    )
    db_session.add(chain)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.trips.get_session_context", mock_ctx):
        # 1. Start flow via CallbackQuery
        cb_query = AsyncMock(spec=CallbackQuery)
        cb_query.data = "trip:new"
        cb_query.message = AsyncMock(spec=Message)
        cb_query.message.chat = Chat(id=chat_id, type="private")
        cb_query.message.edit_text = AsyncMock()
        cb_query.answer = AsyncMock()

        await handle_start_new_trip(cb_query, state)
        assert await state.get_state() == TripStates.selecting_bike

        # 2. Select bike with invalid ID
        invalid_query = AsyncMock(spec=CallbackQuery)
        invalid_query.data = "trip:bike:invalid-uuid"
        invalid_query.message = AsyncMock(spec=Message)
        invalid_query.answer = AsyncMock()
        await handle_trip_bike_selected(invalid_query, state)
        invalid_query.answer.assert_called_with("Invalid bike ID", show_alert=True)

        # 3. Select bike with valid ID
        valid_query = AsyncMock(spec=CallbackQuery)
        valid_query.data = f"trip:bike:{bike.id}"
        valid_query.message = AsyncMock(spec=Message)
        valid_query.message.edit_text = AsyncMock()
        valid_query.answer = AsyncMock()
        await handle_trip_bike_selected(valid_query, state)
        assert await state.get_state() == TripStates.entering_distance

        # 4. Enter invalid distance
        msg_dist_inv = AsyncMock(spec=Message)
        msg_dist_inv.text = "abc"
        msg_dist_inv.answer = AsyncMock()
        await handle_trip_distance_entered(msg_dist_inv, state)
        assert await state.get_state() == TripStates.entering_distance

        # 5. Enter valid distance (50 km)
        msg_dist = AsyncMock(spec=Message)
        msg_dist.text = "50.0"
        msg_dist.answer = AsyncMock()
        await handle_trip_distance_entered(msg_dist, state)
        assert await state.get_state() == TripStates.entering_elevation

        # 6. Select elevation preset (500m)
        elev_query = AsyncMock(spec=CallbackQuery)
        elev_query.data = "preset_elev:500"
        elev_query.from_user = TgUser(id=chat_id, is_bot=False, first_name="Rider")
        elev_query.message = AsyncMock(spec=Message)
        elev_query.message.chat = Chat(id=chat_id, type="private")
        elev_query.message.edit_text = AsyncMock()
        elev_query.answer = AsyncMock()

        await handle_trip_elevation_preset(elev_query, state)

    # Verify state is cleared
    assert await state.get_state() is None

    # Verify bike mileage updated
    updated_bike = (await db_session.execute(select(Bike).where(Bike.id == bike.id))).scalar_one()
    assert updated_bike.total_distance_m == 150_000  # 100km + 50km

    # Verify component wear points increased
    updated_chain = (
        await db_session.execute(select(Component).where(Component.id == chain.id))
    ).scalar_one()
    assert updated_chain.current_wear_points > Decimal("100.00")


@pytest.mark.asyncio
async def test_trip_elevation_text_entry(db_session: AsyncSession) -> None:
    """Verify entering elevation via text message."""
    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        telegram_chat_id=chat_id,
        first_name="Climber",
        strava_athlete_id=random.randint(100_000, 999_999),
        settings={"language": "en"},
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g_trip_{uuid.uuid4().hex[:8]}",
        name="Climbing Machine",
        bike_type=BikeType.GRAVEL,
        total_distance_m=0,
        is_active=True,
    )
    db_session.add(bike)
    await db_session.commit()

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id))
    await state.set_state(TripStates.entering_elevation)
    await state.update_data(bike_id=str(bike.id), distance_km=30.0, language="en")

    mock_ctx = MagicMock()
    mock_ctx.return_value.__aenter__.return_value = db_session
    mock_ctx.return_value.__aexit__.return_value = None

    with patch("velopulse.bot.handlers.trips.get_session_context", mock_ctx):
        # Invalid elevation input
        invalid_msg = AsyncMock(spec=Message)
        invalid_msg.text = "invalid"
        invalid_msg.answer = AsyncMock()
        await handle_trip_elevation_text(invalid_msg, state)
        assert await state.get_state() == TripStates.entering_elevation

        # Valid elevation input
        valid_msg = AsyncMock(spec=Message)
        valid_msg.text = "750"
        valid_msg.chat = Chat(id=chat_id, type="private")
        valid_msg.from_user = TgUser(id=chat_id, is_bot=False, first_name="Climber")
        valid_msg.answer = AsyncMock()
        await handle_trip_elevation_text(valid_msg, state)

    assert await state.get_state() is None
