"""Integration tests for Bike maintenance and history API endpoints."""

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType, MaintenanceType
from velopulse.db.models.maintenance import MaintenanceLog
from velopulse.db.models.user import User


@pytest.mark.asyncio
async def test_get_bike_maintenance_not_found(async_client: AsyncClient) -> None:
    """Verify 404 response for non-existent bike."""
    random_uuid = uuid.uuid4()
    resp = await async_client.get(f"/api/v1/bikes/{random_uuid}/maintenance")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_bike_maintenance_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify 200 response with aggregated maintenance history and items."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Filippo",
        last_name="Ganna",
        access_token="tok",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Pinarello Bolide TT",
        bike_type=BikeType.TT,
        total_distance_m=500_000,  # 500.0 km
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Dura-Ace TT",
        lifespan_wear_points=Decimal("3000.00"),
    )
    db_session.add(comp)
    await db_session.flush()

    log = MaintenanceLog(
        user_id=user.id,
        component_id=comp.id,
        log_type=MaintenanceType.CLEAN_AND_LUBE,
        description="Hot melt paraffin wax treatment",
        cost=Decimal("20.00"),
        odometer_km=Decimal("500.00"),
    )
    db_session.add(log)
    await db_session.commit()

    resp = await async_client.get(f"/api/v1/bikes/{bike.id}/maintenance")
    assert resp.status_code == 200
    data = resp.json()

    assert data["bike_id"] == str(bike.id)
    assert data["bike_name"] == "Pinarello Bolide TT"
    assert float(data["total_distance_km"]) == 500.0
    assert float(data["total_cost"]) == 20.0
    assert data["total_events"] == 1
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["component_id"] == str(comp.id)
    assert item["component_type"] == "chain"
    assert item["log_type"] == "clean_and_lube"
    assert item["description"] == "Hot melt paraffin wax treatment"
    assert float(item["cost"]) == 20.0


@pytest.mark.asyncio
async def test_get_bike_maintenance_filter_and_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify log_type filtering and pagination query params on maintenance history."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Remco",
        access_token="tok",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Specialized Tarmac SL8",
        bike_type=BikeType.ROAD,
        total_distance_m=800_000,
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.FRONT_BRAKE_PAD,
        brand_model="SRAM Red AXS Pads",
        lifespan_wear_points=Decimal("2500.00"),
    )
    db_session.add(comp)
    await db_session.flush()

    # Add 2 logs: 1 repair, 1 inspect_tune
    log1 = MaintenanceLog(
        user_id=user.id,
        component_id=comp.id,
        log_type=MaintenanceType.REPAIR,
        cost=Decimal("35.00"),
    )
    log2 = MaintenanceLog(
        user_id=user.id,
        component_id=comp.id,
        log_type=MaintenanceType.INSPECT_TUNE,
        cost=Decimal("15.00"),
    )
    db_session.add_all([log1, log2])
    await db_session.commit()

    # Filter for repair only
    resp = await async_client.get(
        f"/api/v1/bikes/{bike.id}/maintenance?log_type=repair"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["log_type"] == "repair"

    # Pagination: limit=1
    resp_limit = await async_client.get(
        f"/api/v1/bikes/{bike.id}/maintenance?limit=1"
    )
    assert resp_limit.status_code == 200
    assert len(resp_limit.json()["items"]) == 1
    assert resp_limit.json()["total_events"] == 2


@pytest.mark.asyncio
async def test_record_maintenance_api_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify POST /api/v1/bikes/{bike_id}/maintenance records a log event."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Kasper",
        access_token="tok",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Canyon Grizl",
        bike_type=BikeType.GRAVEL,
        total_distance_m=200_000,
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.REAR_TIRE,
        brand_model="Maxxis Rambler 45c",
        lifespan_wear_points=Decimal("4000.00"),
    )
    db_session.add(comp)
    await db_session.commit()

    payload = {
        "component_id": str(comp.id),
        "log_type": "inspect_tune",
        "description": "Tubeless sealant top-up (60ml Stan's NoTubes)",
        "cost": "8.50",
    }
    resp = await async_client.post(
        f"/api/v1/bikes/{bike.id}/maintenance",
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["component_id"] == str(comp.id)
    assert data["log_type"] == "inspect_tune"
    assert float(data["cost"]) == 8.50
    assert float(data["odometer_km"]) == 200.0


@pytest.mark.asyncio
async def test_replace_component_api_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify POST /api/v1/bikes/{bike_id}/replace retires old component and creates new."""
    athlete_id = random.randint(10_000_000, 99_999_999)
    user = User(
        strava_athlete_id=athlete_id,
        first_name="Tom",
        access_token="tok",
        refresh_token="ref",
        token_expires_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.flush()

    bike = Bike(
        user_id=user.id,
        strava_gear_id=f"g{athlete_id}",
        name="Pinarello Dogma F",
        bike_type=BikeType.ROAD,
        total_distance_m=450_000,
    )
    db_session.add(bike)
    await db_session.flush()

    comp = Component(
        bike_id=bike.id,
        component_type=ComponentType.CHAIN,
        brand_model="Shimano Ultegra 12s",
        lifespan_wear_points=Decimal("2800.00"),
        current_wear_points=Decimal("2850.00"),
        status=ComponentStatus.REPLACE_RECOMMENDED,
    )
    db_session.add(comp)
    await db_session.commit()

    payload = {
        "component_id": str(comp.id),
        "new_brand_model": "Shimano Dura-Ace 12s",
        "new_lifespan_wear_points": "3200.00",
        "cost": "65.00",
        "description": "Replaced Ultegra with Dura-Ace chain",
    }
    resp = await async_client.post(
        f"/api/v1/bikes/{bike.id}/replace",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["log_type"] == "replace"
    assert data["brand_model"] == "Shimano Dura-Ace 12s"
    assert float(data["cost"]) == 65.00
    assert data["component_id"] != str(comp.id)
