"""Activity persistence model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from velopulse.db.base import Base

if TYPE_CHECKING:
    from velopulse.db.models.bike import Bike
    from velopulse.db.models.user import User
    from velopulse.db.models.wear import ActivityComponentWear


class Activity(Base):
    """Activity entity representing an ingested cycling workout/ride."""

    __tablename__ = "activities"

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
    bike_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bikes.id", ondelete="SET NULL"),
        nullable=True,
    )
    strava_activity_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    activity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Ride",
        server_default=text("'Ride'"),
    )
    distance_m: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    moving_time_s: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    total_elevation_m: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    start_latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )
    start_longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_weather_enriched: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    weather_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="activities",
    )
    bike: Mapped["Bike | None"] = relationship(
        "Bike",
        back_populates="activities",
    )
    wear_records: Mapped[list["ActivityComponentWear"]] = relationship(
        "ActivityComponentWear",
        back_populates="activity",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_activities_bike_start", "bike_id", text("start_time DESC")),
        Index(
            "idx_activities_pending_weather",
            "id",
            postgresql_where=text("is_weather_enriched = false"),
        ),
    )
