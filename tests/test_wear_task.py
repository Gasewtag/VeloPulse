"""Tests for Taskiq calculate_wear_task."""

import random
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
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType
from velopulse.db.models.user import User
from velopulse.db.models.wear import ActivityComponentWear
from velopulse.tasks.wear import calculate_wear_task


@pytest.fixture
def mock_redis() -> Generator[MagicMock, None, None]:
    with patch("velopulse.tasks.wear.Redis") as mock_redis_cls:
        redis_instance = MagicMock()
        mock_redis_cls.from_url.return_value = redis_instance
        lock_mock = AsyncMock()
        lock_mock.__aenter__.return_value = lock_mock
        redis_instance.lock.return_value = lock_mock
        redis_instance.aclose = AsyncMock()
        yield redis_instance


@pytest.mark.asyncio
async def test_calculate_wear_task_success(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Verify calculate_wear_task attributes wear and updates components and bike mileage."""
    athlete_id = random.randint(100000, 999999)
    act_id = random.randint(100000, 999999)

    user = User(
        strava_athlete_id=athlete_id,
        first_name="Rider",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{athlete_id}",
        name="Aero Road Machine",
        bike_type=BikeType.ROAD,
        total_distance_m=0,
        total_elevation_m=0,
    )
    db_session.add(bike)
    await db_session.flush()

    chain = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Dura-Ace 12s",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("500.00"),
        status=ComponentStatus.OPTIMAL,
    )
    pads = Component(
        bike_id=bike.id,
        component_type=ComponentType.FRONT_BRAKE_PAD,
        brand_model="Shimano L05A Resin",
        lifespan_wear_points=Decimal("2000.00"),
        current_wear_points=Decimal("800.00"),
        status=ComponentStatus.OPTIMAL,
    )
    db_session.add_all([chain, pads])
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        bike_id=bike.id,
        strava_activity_id=act_id,
        name="Hilly Sunday Ride",
        distance_m=Decimal("60000.00"),  # 60 km
        moving_time_s=7200,
        total_elevation_m=Decimal("600.00"),
        start_latitude=Decimal("52.520000"),
        start_longitude=Decimal("13.410000"),
        start_time=datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
        is_weather_enriched=True,
        weather_data={"weather_multiplier": 1.4, "surface_condition": "DAMP"},
    )
    db_session.add(activity)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.tasks.wear.get_session_context", mock_session_local):
        await calculate_wear_task(activity.id)

    # 1. Verify ActivityComponentWear records
    stmt = select(ActivityComponentWear).where(ActivityComponentWear.activity_id == activity.id)
    records = list((await db_session.execute(stmt)).scalars().all())
    assert len(records) == 2

    # 2. Verify Component wear points increased
    c_res = await db_session.execute(select(Component).where(Component.id == chain.id))
    updated_chain = c_res.scalar_one()
    assert updated_chain.current_wear_points > Decimal("500.00")

    p_res = await db_session.execute(select(Component).where(Component.id == pads.id))
    updated_pads = p_res.scalar_one()
    assert updated_pads.current_wear_points > Decimal("800.00")

    # 3. Verify Bike totals updated
    b_res = await db_session.execute(select(Bike).where(Bike.id == bike.id))
    updated_bike = b_res.scalar_one()
    assert updated_bike.total_distance_m == 60000
    assert updated_bike.total_elevation_m == 600


@pytest.mark.asyncio
async def test_calculate_wear_task_idempotency(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Verify re-running task on already attributed activity is a safe no-op."""
    athlete_id = random.randint(100000, 999999)
    act_id = random.randint(100000, 999999)

    user = User(
        strava_athlete_id=athlete_id,
        first_name="IdempotentUser",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"gear_{athlete_id}",
        name="Idempotent Bike",
        bike_type=BikeType.ROAD,
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="KMC",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("100.00"),
    )
    db_session.add(comp)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        bike_id=bike.id,
        strava_activity_id=act_id,
        name="Idempotent Ride",
        distance_m=Decimal("10000.00"),
        moving_time_s=1200,
        total_elevation_m=Decimal("50.00"),
        start_latitude=Decimal("52.520000"),
        start_longitude=Decimal("13.410000"),
        start_time=datetime(2026, 8, 16, 9, 0, tzinfo=UTC),
        is_weather_enriched=True,
        weather_data={"weather_multiplier": 1.0},
    )
    db_session.add(activity)
    await db_session.flush()

    # Pre-insert attribution record
    prior_attribution = ActivityComponentWear(
        activity_id=activity.id,
        component_id=comp.id,
        wear_delta=Decimal("10.00"),
        base_distance_km=Decimal("10.00"),
        elevation_factor=Decimal("1.00"),
        weather_factor=Decimal("1.00"),
    )
    db_session.add(prior_attribution)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.tasks.wear.get_session_context", mock_session_local):
        await calculate_wear_task(activity.id)

    # Count must remain 1
    stmt = select(ActivityComponentWear).where(ActivityComponentWear.activity_id == activity.id)
    records = list((await db_session.execute(stmt)).scalars().all())
    assert len(records) == 1

    # Component wear points should not be modified
    c_res = await db_session.execute(select(Component).where(Component.id == comp.id))
    assert c_res.scalar_one().current_wear_points == Decimal("100.00")


@pytest.mark.asyncio
async def test_calculate_wear_task_no_bike(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Verify task gracefully exits if activity has no bike associated."""
    athlete_id = random.randint(100000, 999999)
    act_id = random.randint(100000, 999999)

    user = User(
        strava_athlete_id=athlete_id,
        first_name="NoBikeUser",
        access_token="token",
        refresh_token=encrypt_token("refresh"),
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        bike_id=None,
        strava_activity_id=act_id,
        name="No Bike Ride",
        distance_m=Decimal("20000.00"),
        moving_time_s=2400,
        total_elevation_m=Decimal("100.00"),
        start_latitude=None,
        start_longitude=None,
        start_time=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
    )
    db_session.add(activity)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with patch("velopulse.tasks.wear.get_session_context", mock_session_local):
        # Should not raise exception
        await calculate_wear_task(activity.id)

    stmt = select(ActivityComponentWear).where(ActivityComponentWear.activity_id == activity.id)
    records = list((await db_session.execute(stmt)).scalars().all())
    assert len(records) == 0
