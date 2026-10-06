"""Tests for MaintenanceService core domain operations."""

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType, MaintenanceType
from velopulse.db.models.user import User
from velopulse.services.maintenance import (
    ComponentAlreadyRetiredError,
    EntityNotFoundError,
    MaintenanceService,
    PermissionDeniedError,
)


@pytest.fixture
def maintenance_service() -> MaintenanceService:
    """Fixture returning a fresh MaintenanceService instance."""
    return MaintenanceService()


@pytest.mark.asyncio
async def test_record_maintenance_success(
    db_session: AsyncSession,
    maintenance_service: MaintenanceService,
) -> None:
    """Verify recording maintenance on a component logs details and computes odometer."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Matthieu",
        last_name="VDPOEL",
        access_token="token",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Canyon Aeroad CFR",
        bike_type=BikeType.ROAD,
        total_distance_m=125_000,  # 125.0 km
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Dura-Ace 12s",
        lifespan_wear_points=Decimal("3000.00"),
        current_wear_points=Decimal("850.00"),
        status=ComponentStatus.OPTIMAL,
    )
    db_session.add(comp)
    await db_session.flush()

    # Record Clean & Lube
    _comp, log = await maintenance_service.record_maintenance(
        session=db_session,
        user_id=user.id,
        component_id=comp.id,
        log_type=MaintenanceType.CLEAN_AND_LUBE,
        description="Degreased and applied Squirt wax",
        cost=Decimal("12.50"),
    )
    await db_session.flush()

    assert log.id is not None
    assert log.component_id == comp.id
    assert log.user_id == user.id
    assert log.log_type == MaintenanceType.CLEAN_AND_LUBE
    assert log.description == "Degreased and applied Squirt wax"
    assert log.cost == Decimal("12.50")
    assert log.odometer_km == Decimal("125.00")


@pytest.mark.asyncio
async def test_record_maintenance_not_found_or_unowned(
    db_session: AsyncSession,
    maintenance_service: MaintenanceService,
) -> None:
    """Verify EntityNotFoundError and PermissionDeniedError on unauthorized components."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user1 = User(
        strava_athlete_id=athlete_id,
        first_name="User1",
        access_token="tok1",
        refresh_token="ref1",
        token_expires_at=datetime.now(UTC),
    )
    user2 = User(
        strava_athlete_id=athlete_id + 1,
        first_name="User2",
        access_token="tok2",
        refresh_token="ref2",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add_all([user1, user2])
    await db_session.flush()

    bike = Bike(
        user_id=user1.id,
        strava_gear_id=f"g{athlete_id}",
        name="Bike 1",
        bike_type=BikeType.ROAD,
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.FRONT_TIRE,
        brand_model="Continental GP5000 28mm",
        lifespan_wear_points=Decimal("5000.00"),
    )
    db_session.add(comp)
    await db_session.flush()

    # Non-existent component
    with pytest.raises(EntityNotFoundError):
        await maintenance_service.record_maintenance(
            session=db_session,
            user_id=user1.id,
            component_id=uuid.uuid4(),
            log_type=MaintenanceType.INSPECT_TUNE,
        )

    # Component owned by user1, operated by user2
    with pytest.raises(PermissionDeniedError):
        await maintenance_service.record_maintenance(
            session=db_session,
            user_id=user2.id,
            component_id=comp.id,
            log_type=MaintenanceType.INSPECT_TUNE,
        )


@pytest.mark.asyncio
async def test_replace_component_workflow(
    db_session: AsyncSession,
    maintenance_service: MaintenanceService,
) -> None:
    """Verify component replacement archives old part, installs new part, and resets wear."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Wout",
        access_token="tok",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Cervelo S5",
        bike_type=BikeType.ROAD,
        total_distance_m=350_000,
    )
    db_session.add(bike)
    await db_session.flush()

    old_comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="KMC X12",
        lifespan_wear_points=Decimal("2500.00"),
        current_wear_points=Decimal("2650.00"),
        status=ComponentStatus.REPLACE_RECOMMENDED,
    )
    db_session.add(old_comp)
    await db_session.flush()

    old_res, new_res, log = await maintenance_service.replace_component(
        session=db_session,
        user_id=user.id,
        component_id=old_comp.id,
        new_brand_model="Shimano CN-M9100",
        new_lifespan_wear_points=Decimal("3000.00"),
        cost=Decimal("45.00"),
        description="Replaced worn chain before mountain stage",
    )
    await db_session.flush()

    # 1. Old component must be retired
    assert old_res.id == old_comp.id
    assert old_res.status == ComponentStatus.RETIRED
    assert old_res.retired_at is not None
    assert old_res.current_wear_points == Decimal("2650.00")  # wear preserved

    # 2. New component must be active with 0 WP
    assert new_res.id != old_comp.id
    assert new_res.bike_id == bike.id
    assert new_res.component_type == ComponentType.CHAIN
    assert new_res.brand_model == "Shimano CN-M9100"
    assert new_res.lifespan_wear_points == Decimal("3000.00")
    assert new_res.current_wear_points == Decimal("0.00")
    assert new_res.status == ComponentStatus.NEW
    assert new_res.retired_at is None

    # 3. Replacement log verified
    assert log.component_id == new_res.id
    assert log.log_type == MaintenanceType.REPLACE
    assert log.cost == Decimal("45.00")
    assert log.odometer_km == Decimal("350.00")

    # 4. Attempting to replace already retired component fails
    with pytest.raises(ComponentAlreadyRetiredError):
        await maintenance_service.replace_component(
            session=db_session,
            user_id=user.id,
            component_id=old_comp.id,
        )


@pytest.mark.asyncio
async def test_get_bike_maintenance_history_aggregation(
    db_session: AsyncSession,
    maintenance_service: MaintenanceService,
) -> None:
    """Verify aggregated timeline, total cost, and event count across all parts on a bike."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Tadej",
        access_token="tok",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Colnago V4Rs",
        bike_type=BikeType.ROAD,
        total_distance_m=1_200_000,  # 1200 km
    )
    db_session.add(bike)
    await db_session.flush()

    chain = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Campagnolo Super Record 12s",
        lifespan_wear_points=Decimal("3500.00"),
    )
    pad = Component(
        bike_id=bike.id,
        component_type=ComponentType.FRONT_BRAKE_PAD,
        brand_model="Campagnolo Disc Pad 03",
        lifespan_wear_points=Decimal("2000.00"),
    )
    db_session.add_all([chain, pad])
    await db_session.flush()

    # Add logs: 1 on chain, 1 on pad
    await maintenance_service.record_maintenance(
        session=db_session,
        user_id=user.id,
        component_id=chain.id,
        log_type=MaintenanceType.CLEAN_AND_LUBE,
        cost=Decimal("15.00"),
        description="Chain wash and wax",
    )
    await maintenance_service.record_maintenance(
        session=db_session,
        user_id=user.id,
        component_id=pad.id,
        log_type=MaintenanceType.INSPECT_TUNE,
        cost=Decimal("25.50"),
        description="Brake caliper piston bleed & pad inspection",
    )
    await db_session.flush()

    history = await maintenance_service.get_bike_maintenance_history(
        session=db_session,
        bike_id=bike.id,
        user_id=user.id,
    )

    assert history.bike_id == bike.id
    assert history.bike_name == "Colnago V4Rs"
    assert history.total_distance_km == Decimal("1200.00")
    assert history.total_events == 2
    assert history.total_cost == Decimal("40.50")
    assert len(history.logs) == 2

    # Test filtering by log_type
    lube_history = await maintenance_service.get_bike_maintenance_history(
        session=db_session,
        bike_id=bike.id,
        user_id=user.id,
        log_type=MaintenanceType.CLEAN_AND_LUBE,
    )
    assert lube_history.total_events == 1
    assert lube_history.total_cost == Decimal("15.00")
    assert len(lube_history.logs) == 1
    assert lube_history.logs[0].component_type == ComponentType.CHAIN


@pytest.mark.asyncio
async def test_adjust_wear_points(
    db_session: AsyncSession,
    maintenance_service: MaintenanceService,
) -> None:
    """Verify manual wear adjustment recalibrates status and logs inspect/tune event."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Jonas",
        access_token="tok",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Cervelo R5",
        bike_type=BikeType.ROAD,
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CASSETTE,
        brand_model="SRAM Red 10-33T",
        lifespan_wear_points=Decimal("6000.00"),
        current_wear_points=Decimal("5600.00"),
        status=ComponentStatus.REPLACE_RECOMMENDED,
    )
    db_session.add(comp)
    await db_session.flush()

    # Recalibrate to 1000 WP (1000 / 6000 = 16.6% -> OPTIMAL)
    updated_comp, log = await maintenance_service.adjust_wear_points(
        session=db_session,
        user_id=user.id,
        component_id=comp.id,
        new_wear_points=Decimal("1000.00"),
        reason="Visual tooth inspection revealed minimal wear",
    )
    await db_session.flush()

    assert updated_comp.current_wear_points == Decimal("1000.00")
    assert updated_comp.status == ComponentStatus.OPTIMAL
    assert log.log_type == MaintenanceType.INSPECT_TUNE
    assert "Visual tooth inspection revealed minimal wear" in (log.description or "")
