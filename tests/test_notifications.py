"""Tests for NotificationDispatcher and dispatch_notifications_task."""

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.core.security import encrypt_token
from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType
from velopulse.db.models.user import User
from velopulse.services.notifications.dispatcher import NotificationDispatcher
from velopulse.tasks.notifications import dispatch_notifications_task


@pytest.mark.asyncio
async def test_should_suppress_alert_critical_bypass() -> None:
    """Verify REPLACE_RECOMMENDED and RETIRED always bypass anti-fatigue cooldown."""
    dispatcher = NotificationDispatcher(bot=AsyncMock())
    comp_id = uuid.uuid4()

    # Even if in cooldown, critical status must return False (not suppressed)
    suppressed = await dispatcher.should_suppress_alert(
        comp_id, ComponentStatus.REPLACE_RECOMMENDED
    )
    assert suppressed is False

    suppressed = await dispatcher.should_suppress_alert(comp_id, ComponentStatus.RETIRED)
    assert suppressed is False


@pytest.mark.asyncio
async def test_should_suppress_alert_cooldown() -> None:
    """Verify ATTENTION_NEEDED obeys 7-day anti-fatigue cooldown via Redis."""
    mock_redis = AsyncMock()
    # First call: not cached (exists -> False)
    mock_redis.exists.return_value = False

    dispatcher = NotificationDispatcher(bot=AsyncMock(), redis_client=mock_redis)
    comp_id = uuid.uuid4()

    suppressed = await dispatcher.should_suppress_alert(comp_id, ComponentStatus.ATTENTION_NEEDED)
    assert suppressed is False
    mock_redis.set.assert_called_once()

    # Second call: active cooldown exists (exists -> True)
    mock_redis.exists.return_value = True
    suppressed_again = await dispatcher.should_suppress_alert(
        comp_id, ComponentStatus.ATTENTION_NEEDED
    )
    assert suppressed_again is True


@pytest.mark.asyncio
async def test_dispatch_wear_alert_no_telegram() -> None:
    """Verify dispatch skips sending when athlete has no telegram_chat_id."""
    dispatcher = NotificationDispatcher(bot=AsyncMock())
    user = User(
        strava_athlete_id=12345,
        first_name="NoTelegram",
        access_token="tok",
        refresh_token=encrypt_token("ref"),
        token_expires_at=datetime.now(UTC),
        telegram_chat_id=None,
    )
    bike = Bike(name="Speedmax", bike_type=BikeType.ROAD)
    activity = Activity(name="Morning Ride", distance_m=Decimal("50000.00"))
    comp = Component(
        component_type=ComponentType.CHAIN,
        brand_model="KMC X11",
        lifespan_wear_points=Decimal("3000"),
        current_wear_points=Decimal("2600"),
        status=ComponentStatus.ATTENTION_NEEDED,
    )

    result = await dispatcher.dispatch_wear_alert(user, bike, activity, [comp])
    assert result is False
    dispatcher.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_wear_alert_success() -> None:
    """Verify dispatch formats message and calls bot.send_message with action buttons."""
    mock_bot = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.exists.return_value = False

    dispatcher = NotificationDispatcher(bot=mock_bot, redis_client=mock_redis)
    user = User(
        strava_athlete_id=54321,
        first_name="ActiveRider",
        access_token="tok",
        refresh_token=encrypt_token("ref"),
        token_expires_at=datetime.now(UTC),
        telegram_chat_id=999888,
    )
    bike = Bike(name="Gravel Grinder", bike_type=BikeType.GRAVEL)
    activity = Activity(name="Dusty Trail", distance_m=Decimal("45000.00"))
    comp = Component(
        id=uuid.uuid4(),
        component_type=ComponentType.CHAIN,
        brand_model="SRAM Eagle 12s",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("2700.00"),
        status=ComponentStatus.ATTENTION_NEEDED,
    )

    result = await dispatcher.dispatch_wear_alert(user, bike, activity, [comp])
    assert result is True

    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == 999888
    assert "Gravel Grinder" in call_kwargs["text"]
    assert "SRAM Eagle 12s" in call_kwargs["text"]
    assert "90.0%" in call_kwargs["text"]
    assert call_kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_dispatch_notifications_task_success(db_session: AsyncSession) -> None:
    """Verify dispatch_notifications_task queries activity, resolves components, and dispatches."""
    athlete_id = random.randint(100000, 999999)
    act_id = random.randint(100000, 999999)

    chat_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="TaskRider",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
        telegram_chat_id=chat_id,
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{athlete_id}",
        name="Aero Bike",
        bike_type=BikeType.ROAD,
        total_distance_m=1000000,
        total_elevation_m=5000,
    )
    db_session.add(bike)
    await db_session.flush()

    worn_chain = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano HG-901",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("2800.00"),
        status=ComponentStatus.ATTENTION_NEEDED,
    )
    optimal_cassette = Component(
        bike_id=bike.id,
        component_type=ComponentType.CASSETTE,
        brand_model="Shimano Ultegra 11-30",
        lifespan_wear_points=Decimal("8000.00"),
        current_wear_points=Decimal("1000.00"),
        status=ComponentStatus.OPTIMAL,
    )
    db_session.add_all([worn_chain, optimal_cassette])
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        bike_id=bike.id,
        strava_activity_id=act_id,
        name="Fast Group Ride",
        distance_m=Decimal("75000.00"),
        moving_time_s=8000,
        total_elevation_m=Decimal("800.00"),
        start_latitude=Decimal("52.520000"),
        start_longitude=Decimal("13.410000"),
        start_time=datetime(2026, 8, 20, 8, 30, tzinfo=UTC),
    )
    db_session.add(activity)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    mock_redis = MagicMock()
    mock_lock = AsyncMock()
    mock_lock.__aenter__.return_value = mock_lock
    mock_lock.__aexit__.return_value = None
    mock_redis.lock.return_value = mock_lock
    mock_redis.aclose = AsyncMock()

    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch_wear_alert = AsyncMock(return_value=True)
    mock_dispatcher.close = AsyncMock()

    with (
        patch("velopulse.tasks.notifications.Redis.from_url", return_value=mock_redis),
        patch("velopulse.tasks.notifications.get_session_context", mock_session_local),
        patch("velopulse.tasks.notifications.NotificationDispatcher", return_value=mock_dispatcher),
    ):
        await dispatch_notifications_task(activity.id)

    mock_dispatcher.dispatch_wear_alert.assert_called_once()
    call_kwargs = mock_dispatcher.dispatch_wear_alert.call_args[1]
    assert call_kwargs["user"].id == user.id
    assert call_kwargs["bike"].id == bike.id
    # Only worn_chain should be passed (ATTENTION_NEEDED), not optimal_cassette
    assert len(call_kwargs["components_to_alert"]) == 1
    assert call_kwargs["components_to_alert"][0].id == worn_chain.id
