"""Maintenance domain models and event schemas."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from velopulse.db.models.enums import ComponentType, MaintenanceType


class MaintenanceLogEntry(BaseModel):
    """Domain model representing an individual maintenance event."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    component_id: uuid.UUID
    component_type: ComponentType
    brand_model: str
    user_id: uuid.UUID
    log_type: MaintenanceType
    description: str | None = None
    cost: Decimal = Field(default=Decimal("0.00"))
    odometer_km: Decimal | None = None
    performed_at: datetime
    created_at: datetime


class BikeMaintenanceHistory(BaseModel):
    """Aggregate maintenance history and audit trail for a bicycle."""

    model_config = ConfigDict(extra="ignore")

    bike_id: uuid.UUID
    bike_name: str
    total_distance_km: Decimal
    total_cost: Decimal = Field(default=Decimal("0.00"))
    total_events: int = 0
    logs: list[MaintenanceLogEntry] = Field(default_factory=list)


class ComponentReplacementResult(BaseModel):
    """Result of component replacement workflow archiving old part and provisioning new."""

    model_config = ConfigDict(extra="ignore")

    old_component_id: uuid.UUID
    new_component_id: uuid.UUID
    maintenance_log_id: uuid.UUID
    bike_id: uuid.UUID
    component_type: ComponentType
    brand_model: str
    performed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
