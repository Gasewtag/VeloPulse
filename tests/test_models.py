"""Tests for SQLAlchemy 2.0 Async declarative database models and schema constraints."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.models import (
    Activity,
    ActivityComponentWear,
    Bike,
    BikeType,
    Component,
    ComponentStatus,
    ComponentType,
    MaintenanceLog,
    MaintenanceType,
    User,
)


@pytest.mark.asyncio
async def test_user_crud_and_defaults(db_session: AsyncSession) -> None:
    """Ensure User entity supports create, read, update, and uses proper defaults."""
    unique_strava_id = int(uuid.uuid4().int % 1_000_000_000)
    user = User(
        strava_athlete_id=unique_strava_id,
        first_name="Wout",
        last_name="van Aert",
        access_token="initial-access-token",
        refresh_token="initial-refresh-token",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    assert user.id is not None
    assert user.first_name == "Wout"
    assert user.settings == {"notifications_enabled": True, "weather_enrichment": True}
    assert user.created_at is not None
    assert user.updated_at is not None

    # Update
    user.last_name = "Van Aert"
    await db_session.flush()

    result = await db_session.execute(select(User).where(User.id == user.id))
    fetched_user = result.scalar_one()
    assert fetched_user.last_name == "Van Aert"


@pytest.mark.asyncio
async def test_user_unique_strava_id_constraint(db_session: AsyncSession) -> None:
    """Ensure duplicate strava_athlete_id violates unique constraint."""
    unique_strava_id = int(uuid.uuid4().int % 1_000_000_000)
    user1 = User(
        strava_athlete_id=unique_strava_id,
        first_name="Athlete",
        access_token="token-1",
        refresh_token="ref-1",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user1)
    await db_session.flush()

    user2 = User(
        strava_athlete_id=unique_strava_id,
        first_name="Duplicate Athlete",
        access_token="token-2",
        refresh_token="ref-2",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_bike_creation_and_relationship(db_session: AsyncSession) -> None:
    """Ensure Bike is properly persisted with enum and linked to User."""
    unique_strava_id = int(uuid.uuid4().int % 1_000_000_000)
    user = User(
        strava_athlete_id=unique_strava_id,
        first_name="Tadej",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{unique_strava_id}",
        name="Colnago V4Rs",
        bike_type=BikeType.ROAD,
        brand="Colnago",
        model="V4Rs",
    )
    db_session.add(bike)
    await db_session.flush()

    assert bike.id is not None
    assert bike.bike_type == BikeType.ROAD
    assert bike.is_active is True
    assert bike.total_distance_m == 0
    assert bike.total_elevation_m == 0


@pytest.mark.asyncio
async def test_component_check_constraints(db_session: AsyncSession) -> None:
    """Verify check constraints for lifespan and wear points on Component."""
    unique_strava_id = int(uuid.uuid4().int % 1_000_000_000)
    user = User(
        strava_athlete_id=unique_strava_id,
        first_name="Remco",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{unique_strava_id}",
        name="Specialized Tarmac SL8",
        bike_type=BikeType.ROAD,
    )
    db_session.add(bike)
    await db_session.flush()

    # Valid component
    valid_component = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Dura-Ace 12s",
        lifespan_wear_points=Decimal("5000.00"),
        current_wear_points=Decimal("0.00"),
        status=ComponentStatus.NEW,
    )
    db_session.add(valid_component)
    await db_session.flush()
    assert valid_component.id is not None

    # Invalid lifespan <= 0 (chk_positive_lifespan)
    invalid_component = Component(
        bike_id=bike.id,
        component_type=ComponentType.CASSETTE,
        brand_model="Shimano Ultegra 11-30",
        lifespan_wear_points=Decimal("0.00"),
    )
    db_session.add(invalid_component)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_activity_and_weather_enrichment(db_session: AsyncSession) -> None:
    """Ensure Activity correctly persists spatial, temporal, and weather enrichment metadata."""
    unique_strava_id = int(uuid.uuid4().int % 1_000_000_000)
    user = User(
        strava_athlete_id=unique_strava_id,
        first_name="Mathieu",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{unique_strava_id}",
        name="Canyon Aeroad",
        bike_type=BikeType.ROAD,
    )
    db_session.add(bike)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        bike_id=bike.id,
        strava_activity_id=unique_strava_id,
        name="Tour of Flanders Recce",
        activity_type="Ride",
        distance_m=Decimal("152430.50"),
        moving_time_s=16200,
        total_elevation_m=Decimal("1850.00"),
        start_latitude=Decimal("50.8503"),
        start_longitude=Decimal("4.3517"),
        start_time=datetime.now(UTC),
        is_weather_enriched=True,
        weather_data={"precipitation_mm": 2.5, "temp_c": 8.0, "surface_wetness": 0.8},
    )
    db_session.add(activity)
    await db_session.flush()

    assert activity.id is not None
    assert activity.is_weather_enriched is True
    assert activity.weather_data is not None
    assert activity.weather_data["precipitation_mm"] == 2.5


@pytest.mark.asyncio
async def test_activity_component_wear_attribution(db_session: AsyncSession) -> None:
    """Ensure wear attribution bridges Activity and Component with unique constraint."""
    unique_strava_id = int(uuid.uuid4().int % 1_000_000_000)
    user = User(
        strava_athlete_id=unique_strava_id,
        first_name="Jonas",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{unique_strava_id}",
        name="Cervelo S5",
        bike_type=BikeType.ROAD,
    )
    db_session.add(bike)
    await db_session.flush()

    chain = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="SRAM Red Flattop",
        lifespan_wear_points=Decimal("4000.00"),
    )
    db_session.add(chain)
    await db_session.flush()

    activity = Activity(
        user_id=user.id,
        bike_id=bike.id,
        strava_activity_id=unique_strava_id,
        name="Col du Galibier climb",
        distance_m=Decimal("85000.00"),
        moving_time_s=9800,
        start_time=datetime.now(UTC),
    )
    db_session.add(activity)
    await db_session.flush()

    wear = ActivityComponentWear(
        activity_id=activity.id,
        component_id=chain.id,
        wear_delta=Decimal("120.50"),
        base_distance_km=Decimal("85.00"),
        elevation_factor=Decimal("1.42"),
        weather_factor=Decimal("1.00"),
    )
    db_session.add(wear)
    await db_session.flush()

    assert wear.id is not None
    assert wear.wear_delta == Decimal("120.50")

    # Duplicate attribution must fail unique constraint uq_activity_component
    duplicate_wear = ActivityComponentWear(
        activity_id=activity.id,
        component_id=chain.id,
        wear_delta=Decimal("10.00"),
        base_distance_km=Decimal("85.00"),
    )
    db_session.add(duplicate_wear)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_maintenance_log_and_cascade_delete(db_session: AsyncSession) -> None:
    """Verify MaintenanceLog and cascading deletion when parent User is deleted."""
    unique_strava_id = int(uuid.uuid4().int % 1_000_000_000)
    user = User(
        strava_athlete_id=unique_strava_id,
        first_name="Primoz",
        access_token="token",
        refresh_token="refresh",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{unique_strava_id}",
        name="Specialized Shiv",
        bike_type=BikeType.TT,
    )
    db_session.add(bike)
    await db_session.flush()

    pad = Component(
        bike_id=bike.id,
        component_type=ComponentType.FRONT_BRAKE_PAD,
        brand_model="SwissStop Disc RS",
        lifespan_wear_points=Decimal("2000.00"),
    )
    db_session.add(pad)
    await db_session.flush()

    log = MaintenanceLog(
        component_id=pad.id,
        user_id=user.id,
        log_type=MaintenanceType.CLEAN_AND_LUBE,
        description="Cleaned caliper and lubed pistons",
        cost=Decimal("15.50"),
        odometer_km=Decimal("1200.00"),
    )
    db_session.add(log)
    await db_session.flush()

    assert log.id is not None
    assert log.log_type == MaintenanceType.CLEAN_AND_LUBE

    # Cascade delete verification: deleting User deletes Bike, Component, MaintenanceLog
    await db_session.delete(user)
    await db_session.flush()

    deleted_bike = (
        await db_session.execute(select(Bike).where(Bike.id == bike.id))
    ).scalar_one_or_none()
    deleted_component = (
        await db_session.execute(select(Component).where(Component.id == pad.id))
    ).scalar_one_or_none()
    deleted_log = (
        await db_session.execute(select(MaintenanceLog).where(MaintenanceLog.id == log.id))
    ).scalar_one_or_none()

    assert deleted_bike is None
    assert deleted_component is None
    assert deleted_log is None
