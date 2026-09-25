"""Tests for Taskiq enrich_weather_task."""

import random
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.core.security import encrypt_token
from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.models.enums import BikeType
from velopulse.db.models.user import User
from velopulse.tasks.weather import enrich_weather_task


@pytest.fixture
def mock_redis() -> Generator[MagicMock, None, None]:
    with patch("velopulse.tasks.weather.Redis") as mock_redis_cls:
        redis_instance = MagicMock()
        mock_redis_cls.from_url.return_value = redis_instance
        lock_mock = AsyncMock()
        lock_mock.__aenter__.return_value = lock_mock
        redis_instance.lock.return_value = lock_mock
        redis_instance.aclose = AsyncMock()
        yield redis_instance


@pytest.mark.asyncio
async def test_enrich_weather_task_outdoor_success(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Verify outdoor activity is enriched with valid weather metrics and Wm factor."""
    athlete_id = random.randint(100000, 999999)
    activity_id = random.randint(100000, 999999)

    user = User(
        strava_athlete_id=athlete_id,
        first_name="Outdoor",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{athlete_id}",
        name="Gravel Grinder",
        bike_type=BikeType.GRAVEL,
    )
    db_session.add(bike)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        bike_id=bike.id,
        strava_activity_id=activity_id,
        name="Rainy Morning Gravel",
        distance_m=Decimal("25000.00"),
        moving_time_s=3600,
        total_elevation_m=Decimal("350.00"),
        start_latitude=Decimal("52.520000"),
        start_longitude=Decimal("13.410000"),
        start_time=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        is_weather_enriched=False,
    )
    db_session.add(activity)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.tasks.weather.get_session_context", mock_session_local):
        await enrich_weather_task(activity.id)

    # Verify Activity in DB was enriched
    stmt = select(Activity).where(Activity.id == activity.id)
    res = await db_session.execute(stmt)
    updated = res.scalar_one()

    assert updated.is_weather_enriched is True
    assert updated.weather_data is not None
    assert "surface_condition" in updated.weather_data
    assert "weather_multiplier" in updated.weather_data
    assert updated.weather_data["weather_multiplier"] >= 1.0


@pytest.mark.asyncio
async def test_enrich_weather_task_indoor_success(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Verify indoor activity without GPS is enriched as INDOOR_DRY."""
    athlete_id = random.randint(100000, 999999)
    activity_id = random.randint(100000, 999999)

    user = User(
        strava_athlete_id=athlete_id,
        first_name="Indoor",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        strava_activity_id=activity_id,
        name="Zwift - Watopia Flat Route",
        distance_m=Decimal("20000.00"),
        moving_time_s=2400,
        total_elevation_m=Decimal("50.00"),
        start_latitude=None,
        start_longitude=None,
        start_time=datetime(2026, 9, 21, 18, 0, tzinfo=UTC),
        is_weather_enriched=False,
    )
    db_session.add(activity)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.tasks.weather.get_session_context", mock_session_local):
        await enrich_weather_task(activity.id)

    stmt = select(Activity).where(Activity.id == activity.id)
    res = await db_session.execute(stmt)
    updated = res.scalar_one()

    assert updated.is_weather_enriched is True
    assert updated.weather_data["surface_condition"] == "INDOOR_DRY"
    assert updated.weather_data["weather_multiplier"] == 1.0
    assert updated.weather_data["is_indoor"] is True


@pytest.mark.asyncio
async def test_enrich_weather_task_idempotency(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Verify executing task on an already enriched activity is a safe no-op."""
    athlete_id = random.randint(100000, 999999)
    activity_id = random.randint(100000, 999999)

    user = User(
        strava_athlete_id=athlete_id,
        first_name="Idempotent",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        strava_activity_id=activity_id,
        name="Already Enriched",
        distance_m=Decimal("15000.00"),
        moving_time_s=2000,
        total_elevation_m=Decimal("100.00"),
        start_latitude=Decimal("52.520000"),
        start_longitude=Decimal("13.410000"),
        start_time=datetime(2026, 9, 22, 10, 0, tzinfo=UTC),
        is_weather_enriched=True,
        weather_data={"surface_condition": "DRY", "weather_multiplier": 1.0, "preserved": True},
    )
    db_session.add(activity)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.tasks.weather.get_session_context", mock_session_local):
        await enrich_weather_task(activity.id)

    # Value should remain untouched
    stmt = select(Activity).where(Activity.id == activity.id)
    res = await db_session.execute(stmt)
    updated = res.scalar_one()

    assert updated.weather_data.get("preserved") is True


@pytest.mark.asyncio
async def test_enrich_weather_task_nonexistent_activity(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Verify task gracefully exits if the activity UUID is not found."""
    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.tasks.weather.get_session_context", mock_session_local):
        # Should not raise exception
        await enrich_weather_task(uuid.uuid4())
