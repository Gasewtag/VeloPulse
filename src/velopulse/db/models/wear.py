"""Activity component wear attribution persistence model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from velopulse.db.base import Base

if TYPE_CHECKING:
    from velopulse.db.models.activity import Activity
    from velopulse.db.models.component import Component


class ActivityComponentWear(Base):
    """Wear attribution bridging table mapping accumulated degradation to components per ride."""

    __tablename__ = "activity_component_wear"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    wear_delta: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )
    base_distance_km: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
    )
    elevation_factor: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        nullable=False,
        default=Decimal("1.00"),
        server_default=text("1.00"),
    )
    weather_factor: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        nullable=False,
        default=Decimal("1.00"),
        server_default=text("1.00"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    # Relationships
    activity: Mapped["Activity"] = relationship(
        "Activity",
        back_populates="wear_records",
    )
    component: Mapped["Component"] = relationship(
        "Component",
        back_populates="wear_attributions",
    )

    __table_args__ = (
        UniqueConstraint("activity_id", "component_id", name="uq_activity_component"),
        Index("idx_wear_component_activity", "component_id", "activity_id"),
    )
