"""Physics-based wear calculation service and component state machine."""

import logging

from velopulse.db.models.activity import Activity
from velopulse.db.models.component import Component
from velopulse.db.models.enums import BikeType, ComponentStatus, ComponentType
from velopulse.domain.wear import (
    ActivityWearCalculationResult,
    ComponentWearDelta,
)

logger = logging.getLogger("velopulse.services.wear.service")


class WearCalculationService:
    """Physics-informed component wear point calculation engine."""

    @staticmethod
    def calculate_elevation_factor(
        distance_km: float,
        elevation_gain_m: float,
        bike_type: BikeType | str | None = None,
    ) -> float:
        """Calculate the Elevation & Grade Intensity Factor (Ef).

        Ef = 1.0 + alpha * (delta_H / (D * 10))
        Clamped between [1.0, 2.5].

        Args:
            distance_km: Ride distance in kilometers.
            elevation_gain_m: Total elevation gain in meters.
            bike_type: Bike frame category.

        Returns:
            Elevation factor between 1.0 and 2.5.
        """
        if distance_km <= 0.0:
            return 1.0

        b_type_str = (
            bike_type.value
            if isinstance(bike_type, BikeType)
            else str(bike_type).lower()
            if bike_type
            else ""
        )
        # Grade sensitivity exponent: 0.28 for mountain / gravel, 0.18 for road / other
        alpha = 0.28 if b_type_str in ["mtb", "gravel"] else 0.18

        # Grade metric: delta_H / (D * 10)
        grade_metric = elevation_gain_m / (distance_km * 10.0)
        raw_ef = 1.0 + (alpha * grade_metric)

        return round(max(1.0, min(2.5, raw_ef)), 2)

    @staticmethod
    def calculate_component_coefficient(
        component_type: ComponentType,
        brand_model: str,
        weather_multiplier: float,
        elevation_factor: float,
    ) -> float:
        """Calculate component-specific vulnerability coefficient (Cm).

        Calibrated per ARCHITECTURE.md:
        - Chain: Wm^1.0 * Ef^1.1
        - Cassette: Ef^1.3
        - Chainring: Ef^1.2
        - Brake Pads (Organic/Resin): Wm^1.2
        - Brake Pads (Sintered/Metal): Wm^0.8
        - Rotors: Wm^0.9 * Ef^1.1
        - Front Tire: Wm^0.6 * Ef^1.0
        - Rear Tire: Wm^0.6 * Ef^1.0 * 1.25 (traction & rider weight)
        - Bottom Bracket: Wm^0.8 * Ef^1.2
        - Cables: 1.0
        - Suspension: Ef^1.2
        """
        wm = max(1.0, weather_multiplier)
        ef = max(1.0, elevation_factor)

        c_type = (
            component_type
            if isinstance(component_type, ComponentType)
            else ComponentType(str(component_type).lower())
        )

        model_lower = brand_model.lower() if brand_model else ""

        if c_type == ComponentType.CHAIN:
            cm = (wm**1.0) * (ef**1.1)
        elif c_type == ComponentType.CASSETTE:
            cm = ef**1.3
        elif c_type == ComponentType.CHAINRING:
            cm = ef**1.2
        elif c_type in (ComponentType.FRONT_BRAKE_PAD, ComponentType.REAR_BRAKE_PAD):
            is_metallic = any(kw in model_lower for kw in ["metal", "metallic", "sintered"])
            cm = wm**0.8 if is_metallic else wm**1.2
        elif c_type in (ComponentType.FRONT_ROTOR, ComponentType.REAR_ROTOR):
            cm = (wm**0.9) * (ef**1.1)
        elif c_type == ComponentType.FRONT_TIRE:
            cm = (wm**0.6) * (ef**1.0)
        elif c_type == ComponentType.REAR_TIRE:
            cm = (wm**0.6) * (ef**1.0) * 1.25
        elif c_type == ComponentType.BOTTOM_BRACKET:
            cm = (wm**0.8) * (ef**1.2)
        elif c_type in (ComponentType.SUSPENSION_FORK, ComponentType.REAR_SHOCK):
            cm = ef**1.2
        elif c_type == ComponentType.CABLES:
            cm = 1.0
        else:
            cm = 1.0

        return float(round(max(0.5, cm), 3))

    @staticmethod
    def calculate_wear_delta(
        distance_km: float,
        elevation_factor: float,
        weather_multiplier: float,
        component_coefficient: float,
    ) -> float:
        """Compute accumulated wear points delta: delta_WP = D * Ef * Wm * Cm."""
        if distance_km <= 0.0:
            return 0.0

        delta = distance_km * elevation_factor * weather_multiplier * component_coefficient
        return round(max(0.0, delta), 2)

    @staticmethod
    def evaluate_component_status(
        current_wear_points: float,
        lifespan_wear_points: float,
        previous_status: ComponentStatus = ComponentStatus.NEW,
    ) -> ComponentStatus:
        """Evaluate the lifecycle state machine for a component based on wear percentage."""
        if lifespan_wear_points <= 0.0:
            return ComponentStatus.RETIRED

        ratio = current_wear_points / lifespan_wear_points

        if ratio >= 1.0:
            return ComponentStatus.RETIRED
        elif ratio >= 0.85:
            return ComponentStatus.REPLACE_RECOMMENDED
        elif ratio >= 0.60:
            return ComponentStatus.ATTENTION_NEEDED
        else:
            if current_wear_points == 0.0 and previous_status == ComponentStatus.NEW:
                return ComponentStatus.NEW
            return ComponentStatus.OPTIMAL

    def calculate_activity_wear(
        self,
        activity: Activity,
        components: list[Component],
        bike_type: BikeType | str | None = None,
    ) -> ActivityWearCalculationResult:
        """Calculate wear attributions for all active components on an activity's bike."""
        dist_m = float(activity.distance_m) if activity.distance_m else 0.0
        dist_km = round(dist_m / 1000.0, 2)
        elev_m = float(activity.total_elevation_m) if activity.total_elevation_m else 0.0

        # 1. Elevation Factor
        ef = self.calculate_elevation_factor(dist_km, elev_m, bike_type)

        # 2. Weather Multiplier (from activity.weather_data if enriched)
        wm = 1.0
        if activity.weather_data and isinstance(activity.weather_data, dict):
            wm = float(activity.weather_data.get("weather_multiplier", 1.0))

        deltas: list[ComponentWearDelta] = []
        thresholds_exceeded: list[ComponentWearDelta] = []

        # 3. Attribute wear to each component
        for comp in components:
            prev_wear = float(comp.current_wear_points)
            lifespan = float(comp.lifespan_wear_points)

            cm = self.calculate_component_coefficient(
                comp.component_type, comp.brand_model, wm, ef
            )
            delta_wp = self.calculate_wear_delta(dist_km, ef, wm, cm)
            new_wear = round(prev_wear + delta_wp, 2)

            prev_status = comp.status
            new_status = self.evaluate_component_status(new_wear, lifespan, prev_status)
            status_changed = new_status != prev_status
            wear_pct = round((new_wear / lifespan) * 100.0, 1) if lifespan > 0 else 100.0

            delta_record = ComponentWearDelta(
                component_id=comp.id,
                component_type=comp.component_type,
                brand_model=comp.brand_model,
                wear_delta=delta_wp,
                previous_wear_points=prev_wear,
                new_wear_points=new_wear,
                lifespan_wear_points=lifespan,
                previous_status=prev_status,
                new_status=new_status,
                status_changed=status_changed,
                wear_percentage=wear_pct,
            )
            deltas.append(delta_record)

            # Check if maintenance threshold crossed
            if status_changed and new_status in (
                ComponentStatus.ATTENTION_NEEDED,
                ComponentStatus.REPLACE_RECOMMENDED,
                ComponentStatus.RETIRED,
            ):
                thresholds_exceeded.append(delta_record)

        return ActivityWearCalculationResult(
            activity_id=activity.id,
            bike_id=activity.bike_id or components[0].bike_id,
            distance_km=dist_km,
            elevation_gain_m=elev_m,
            elevation_factor=ef,
            weather_multiplier=wm,
            component_wear_records=deltas,
            thresholds_exceeded=thresholds_exceeded,
        )
