"""Tests for activity ingestion tasks."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.models.user import User
from velopulse.domain.strava import StravaActivityDetailed
from velopulse.tasks.activities import ingest_activity_task


@pytest.fixture
def mock_redis() -> Generator[MagicMock, None, None]:
    with patch("velopulse.tasks.activities.Redis") as mock_redis_cls:
        redis_instance = MagicMock()
        mock_redis_cls.from_url.return_value = redis_instance
        # Mock async context manager for lock
        lock_mock = AsyncMock()
        lock_mock.__aenter__.return_value = lock_mock
        redis_instance.lock.return_value = lock_mock

        # Make aclose an async mock
        redis_instance.aclose = AsyncMock()
        yield redis_instance


@pytest.mark.asyncio
async def test_ingest_activity_task_success(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Test successful ingestion of a new activity."""
    import random

    athlete_id = random.randint(100000, 999999)
    activity_id = random.randint(100000, 999999)

    # Create test user and bike
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Test",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"b_{athlete_id}",
        name="Test Bike",
    )
    db_session.add(bike)
    await db_session.commit()

    # Mock SessionLocal to return our test db_session
    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with (
        patch("velopulse.tasks.activities.get_session_context", mock_session_local),
        patch("velopulse.tasks.activities.StravaAuthService") as mock_auth_cls,
        patch("velopulse.tasks.activities.StravaClient") as mock_client_cls,
    ):
        auth_instance = AsyncMock()
        auth_instance.get_valid_access_token.return_value = "valid_token"
        mock_auth_cls.return_value = auth_instance

        client_instance = AsyncMock()
        client_instance.get_activity.return_value = StravaActivityDetailed(
            id=activity_id,
            name="Morning Ride",
            distance=10000.0,
            moving_time=1800,
            total_elevation_gain=100.0,
            type="Ride",
            sport_type="Ride",
            start_date=datetime.now(UTC),
            start_latlng=[0.0, 0.0],
            gear_id=f"b_{athlete_id}",
        )
        mock_client_cls.return_value = client_instance

        # Run task directly (bypass taskiq broker for unit test)
        await ingest_activity_task(athlete_id, activity_id)

    # Verify Activity was created
    result = await db_session.execute(
        select(Activity).where(Activity.strava_activity_id == activity_id)
    )
    activity = result.scalar_one_or_none()
    assert activity is not None
    assert activity.name == "Morning Ride"
    assert activity.distance_m == 10000.0
    assert activity.bike_id == bike.id
    assert activity.user_id == user.id


@pytest.mark.asyncio
async def test_ingest_activity_task_duplicate(
    db_session: AsyncSession, mock_redis: MagicMock
) -> None:
    """Test duplicate webhook events are safely ignored."""
    import random

    athlete_id = random.randint(100000, 999999)
    activity_id = random.randint(100000, 999999)

    user = User(
        strava_athlete_id=athlete_id,
        first_name="Test",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        strava_activity_id=activity_id,
        name="Existing Ride",
        distance_m=100.0,
        moving_time_s=60,
        start_time=datetime.now(UTC),
    )
    db_session.add(activity)
    await db_session.commit()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = db_session
    mock_session_local.return_value.__aexit__ = AsyncMock()

    with (
        patch("velopulse.tasks.activities.get_session_context", mock_session_local),
        patch("velopulse.tasks.activities.StravaClient") as mock_client_cls,
    ):
        # Task should exit early before calling Strava API
        await ingest_activity_task(athlete_id, activity_id)
        mock_client_cls.return_value.get_activity.assert_not_called()
