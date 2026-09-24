"""Component persistence model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from velopulse.db.base import Base
from velopulse.db.models.enums import ComponentStatus, ComponentType

if TYPE_CHECKING:
    from velopulse.db.models.bike import Bike
    from velopulse.db.models.maintenance import MaintenanceLog
    from velopulse.db.models.wear import ActivityComponentWear


class Component(Base):
    """Component mechanical part attached to a bicycle."""

    __tablename__ = "components"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    bike_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bikes.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_type: Mapped[ComponentType] = mapped_column(
        SAEnum(
            ComponentType,
            name="component_type_enum",
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    brand_model: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    lifespan_wear_points: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    current_wear_points: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    status: Mapped[ComponentStatus] = mapped_column(
        SAEnum(
            ComponentStatus,
            name="component_status_enum",
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=ComponentStatus.NEW,
        server_default=text("'new'"),
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
    )

    # Relationships
    bike: Mapped["Bike"] = relationship(
        "Bike",
        back_populates="components",
    )
    wear_attributions: Mapped[list["ActivityComponentWear"]] = relationship(
        "ActivityComponentWear",
        back_populates="component",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(
        "MaintenanceLog",
        back_populates="component",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("lifespan_wear_points > 0", name="chk_positive_lifespan"),
        CheckConstraint("current_wear_points >= 0", name="chk_positive_wear"),
        Index("idx_components_bike_status", "bike_id", "status"),
        Index(
            "idx_components_active_wear",
            "bike_id",
            "current_wear_points",
            "lifespan_wear_points",
        ),
    )
