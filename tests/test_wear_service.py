"""Tests for WearCalculationService physics formulas and state machine."""

import uuid
from decimal import Decimal

from velopulse.db.models.activity import Activity
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType
from velopulse.services.wear.service import WearCalculationService


def test_calculate_elevation_factor_flat() -> None:
    """Verify flat ride results in baseline Ef=1.00."""
    service = WearCalculationService()
    ef = service.calculate_elevation_factor(distance_km=50.0, elevation_gain_m=0.0, bike_type=BikeType.ROAD)
    assert ef == 1.00


def test_calculate_elevation_factor_moderate_climb() -> None:
    """Verify road climb calculation: Ef = 1.0 + 0.18 * (500 / 500) = 1.18."""
    service = WearCalculationService()
    ef = service.calculate_elevation_factor(
        distance_km=50.0, elevation_gain_m=500.0, bike_type=BikeType.ROAD
    )
    assert ef == 1.18


def test_calculate_elevation_factor_mtb_steep() -> None:
    """Verify mountain bike steeper alpha exponent: Ef = 1.0 + 0.28 * (800 / 200) = 2.12."""
    service = WearCalculationService()
    ef = service.calculate_elevation_factor(
        distance_km=20.0, elevation_gain_m=800.0, bike_type=BikeType.MTB
    )
    assert ef == 2.12


def test_calculate_elevation_factor_boundary_clamped() -> None:
    """Verify extreme elevation gain is clamped to maximum Ef=2.50."""
    service = WearCalculationService()
    ef = service.calculate_elevation_factor(
        distance_km=10.0, elevation_gain_m=3000.0, bike_type=BikeType.ROAD
    )
    assert ef == 2.50


def test_calculate_component_coefficients() -> None:
    """Verify component-specific sensitivity coefficients."""
    service = WearCalculationService()

    # Dry flat baseline (Wm=1.0, Ef=1.0) -> all Cm should be 1.0 (except rear tire which is 1.25)
    assert service.calculate_component_coefficient(ComponentType.CHAIN, "Shimano HG-701", 1.0, 1.0) == 1.0
    assert service.calculate_component_coefficient(ComponentType.CASSETTE, "Shimano Ultegra", 1.0, 1.0) == 1.0
    assert service.calculate_component_coefficient(ComponentType.CABLES, "Jagwire", 1.0, 1.0) == 1.0
    assert service.calculate_component_coefficient(ComponentType.REAR_TIRE, "Continental GP5000", 1.0, 1.0) == 1.25

    # Wet rain ride (Wm=2.0, Ef=1.2)
    # Resin pads: Wm^1.2 = 2.0^1.2 ≈ 2.297
    cm_resin = service.calculate_component_coefficient(ComponentType.FRONT_BRAKE_PAD, "Shimano L05A Resin", 2.0, 1.2)
    # Sintered pads: Wm^0.8 = 2.0^0.8 ≈ 1.741
    cm_metal = service.calculate_component_coefficient(ComponentType.FRONT_BRAKE_PAD, "Shimano Metallic Sintered", 2.0, 1.2)
    assert cm_resin > cm_metal
    assert round(cm_resin, 1) == 2.3
    assert round(cm_metal, 1) == 1.7


def test_evaluate_component_status_lifecycle() -> None:
    """Verify component lifecycle state transitions based on accumulated wear."""
    service = WearCalculationService()
    lifespan = 3000.0

    # 0% wear, was NEW -> remains NEW
    assert service.evaluate_component_status(0.0, lifespan, ComponentStatus.NEW) == ComponentStatus.NEW

    # 10% wear -> OPTIMAL (<60%)
    assert service.evaluate_component_status(300.0, lifespan) == ComponentStatus.OPTIMAL

    # 59% wear -> OPTIMAL
    assert service.evaluate_component_status(1770.0, lifespan) == ComponentStatus.OPTIMAL

    # 65% wear -> ATTENTION_NEEDED (60% <= wear < 85%)
    assert service.evaluate_component_status(1950.0, lifespan) == ComponentStatus.ATTENTION_NEEDED

    # 90% wear -> REPLACE_RECOMMENDED (85% <= wear < 100%)
    assert service.evaluate_component_status(2700.0, lifespan) == ComponentStatus.REPLACE_RECOMMENDED

    # 105% wear -> RETIRED (>= 100%)
    assert service.evaluate_component_status(3150.0, lifespan) == ComponentStatus.RETIRED


def test_calculate_activity_wear_multi_components() -> None:
    """Verify full activity wear calculation across multiple installed components."""
    service = WearCalculationService()

    bike_id = uuid.uuid4()
    activity = Activity(
        id=uuid.uuid4(),
        bike_id=bike_id,
        distance_m=Decimal("50000.00"),  # 50 km
        total_elevation_m=Decimal("500.00"),  # Ef = 1.18
        weather_data={"weather_multiplier": 1.5},  # Wm = 1.5
    )

    chain = Component(
        id=uuid.uuid4(),
        bike_id=bike_id,
        component_type=ComponentType.CHAIN,
        brand_model="KMC X11",
        current_wear_points=Decimal("1700.00"),
        lifespan_wear_points=Decimal("3000.00"),
        status=ComponentStatus.OPTIMAL,
    )

    brake_pads = Component(
        id=uuid.uuid4(),
        bike_id=bike_id,
        component_type=ComponentType.FRONT_BRAKE_PAD,
        brand_model="Organic Resin Pads",
        current_wear_points=Decimal("1650.00"),
        lifespan_wear_points=Decimal("2000.00"),
        status=ComponentStatus.ATTENTION_NEEDED,
    )

    result = service.calculate_activity_wear(
        activity=activity,
        components=[chain, brake_pads],
        bike_type=BikeType.ROAD,
    )

    assert result.distance_km == 50.0
    assert result.elevation_factor == 1.18
    assert result.weather_multiplier == 1.5
    assert len(result.component_wear_records) == 2

    # Check chain attribution
    chain_delta = next(r for r in result.component_wear_records if r.component_id == chain.id)
    assert chain_delta.wear_delta > 50.0  # Multipliers increase wear above raw distance
    assert chain_delta.new_wear_points > 1700.0

    # Brake pads should have crossed from ATTENTION_NEEDED to REPLACE_RECOMMENDED (>85%)
    pads_delta = next(r for r in result.component_wear_records if r.component_id == brake_pads.id)
    assert pads_delta.new_status == ComponentStatus.REPLACE_RECOMMENDED
    assert pads_delta in result.thresholds_exceeded
