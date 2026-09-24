"""Bike persistence model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
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
from velopulse.db.models.enums import BikeType

if TYPE_CHECKING:
    from velopulse.db.models.activity import Activity
    from velopulse.db.models.component import Component
    from velopulse.db.models.user import User


class Bike(Base):
    """Bicycle entity representing athlete equipment."""

    __tablename__ = "bikes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    strava_gear_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    bike_type: Mapped[BikeType] = mapped_column(
        SAEnum(
            BikeType,
            name="bike_type_enum",
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=BikeType.ROAD,
        server_default=text("'road'"),
    )
    brand: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    total_distance_m: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_elevation_m: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
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
    user: Mapped["User"] = relationship(
        "User",
        back_populates="bikes",
    )
    components: Mapped[list["Component"]] = relationship(
        "Component",
        back_populates="bike",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    activities: Mapped[list["Activity"]] = relationship(
        "Activity",
        back_populates="bike",
    )

    __table_args__ = (Index("idx_bikes_user_active", "user_id", "is_active"),)
