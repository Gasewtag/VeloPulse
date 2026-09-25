"""Wear calculation domain models and degradation event schemas."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from velopulse.db.models.enums import ComponentStatus, ComponentType


class ComponentWearDelta(BaseModel):
    """Wear attribution result for an individual bicycle component after a ride."""

    model_config = ConfigDict(extra="ignore")

    component_id: uuid.UUID
    component_type: ComponentType
    brand_model: str
    wear_delta: float  # WP accumulated during this ride
    previous_wear_points: float
    new_wear_points: float
    lifespan_wear_points: float
    previous_status: ComponentStatus
    new_status: ComponentStatus
    status_changed: bool
    wear_percentage: float  # (new_wear_points / lifespan_wear_points) * 100%


class ActivityWearCalculationResult(BaseModel):
    """Aggregate result of physical wear calculation for an entire activity."""

    model_config = ConfigDict(extra="ignore")

    activity_id: uuid.UUID
    bike_id: uuid.UUID
    distance_km: float
    elevation_gain_m: float
    elevation_factor: float
    weather_multiplier: float
    component_wear_records: list[ComponentWearDelta] = Field(default_factory=list)
    thresholds_exceeded: list[ComponentWearDelta] = Field(default_factory=list)


class WearThresholdExceededEvent(BaseModel):
    """Domain event emitted when one or more components cross maintenance thresholds."""

    model_config = ConfigDict(extra="ignore")

    user_id: uuid.UUID
    bike_id: uuid.UUID
    activity_id: uuid.UUID
    critical_components: list[ComponentWearDelta]
    highest_severity_status: ComponentStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
