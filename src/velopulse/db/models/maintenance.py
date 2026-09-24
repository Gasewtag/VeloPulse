"""Maintenance log persistence model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from velopulse.db.base import Base
from velopulse.db.models.enums import MaintenanceType

if TYPE_CHECKING:
    from velopulse.db.models.component import Component
    from velopulse.db.models.user import User


class MaintenanceLog(Base):
    """Maintenance log entry recording service events, tuning, and replacements."""

    __tablename__ = "maintenance_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    log_type: Mapped[MaintenanceType] = mapped_column(
        SAEnum(
            MaintenanceType,
            name="maintenance_type_enum",
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    cost: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    odometer_km: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    # Relationships
    component: Mapped["Component"] = relationship(
        "Component",
        back_populates="maintenance_logs",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="maintenance_logs",
    )

    __table_args__ = (
        Index("idx_logs_component_performed", "component_id", text("performed_at DESC")),
    )
