"""Pydantic schemas for maintenance logging and reporting APIs."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from velopulse.db.models.enums import ComponentType, MaintenanceType


class MaintenanceLogResponse(BaseModel):
    """Schema representing an individual maintenance log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    component_id: uuid.UUID
    component_type: ComponentType
    brand_model: str
    log_type: MaintenanceType
    description: str | None = None
    cost: Decimal = Field(default=Decimal("0.00"))
    odometer_km: Decimal | None = None
    performed_at: datetime
    created_at: datetime


class BikeMaintenanceHistoryResponse(BaseModel):
    """Schema representing the aggregated maintenance history for a bicycle."""

    model_config = ConfigDict(from_attributes=True)

    bike_id: uuid.UUID
    bike_name: str
    total_distance_km: Decimal
    total_cost: Decimal = Field(default=Decimal("0.00"))
    total_events: int = 0
    items: list[MaintenanceLogResponse] = Field(default_factory=list)


class CreateMaintenanceLogRequest(BaseModel):
    """Request payload for recording a maintenance event on a component."""

    model_config = ConfigDict(extra="forbid")

    component_id: uuid.UUID
    log_type: MaintenanceType
    description: str | None = None
    cost: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    odometer_km: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    performed_at: datetime | None = None


class ReplaceComponentRequest(BaseModel):
    """Request payload for retiring a component and installing a replacement."""

    model_config = ConfigDict(extra="forbid")

    component_id: uuid.UUID
    new_brand_model: str | None = None
    new_lifespan_wear_points: Decimal | None = Field(default=None, gt=Decimal("0.00"))
    cost: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    description: str | None = None
    odometer_km: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    performed_at: datetime | None = None
