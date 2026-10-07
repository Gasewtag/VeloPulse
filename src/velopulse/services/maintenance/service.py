"""Maintenance management and audit trail service."""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import ComponentStatus, ComponentType, MaintenanceType
from velopulse.db.models.maintenance import MaintenanceLog
from velopulse.domain.maintenance import (
    BikeMaintenanceHistory,
    MaintenanceLogEntry,
)

logger = logging.getLogger("velopulse.services.maintenance.service")


class MaintenanceError(Exception):
    """Base error for maintenance domain service operations."""


class EntityNotFoundError(MaintenanceError):
    """Raised when bike, component, or user entity cannot be located."""


class PermissionDeniedError(MaintenanceError):
    """Raised when an operation targets an entity not owned by the user."""


class ComponentAlreadyRetiredError(MaintenanceError):
    """Raised when attempting to operate on an already retired component."""


class MaintenanceService:
    """Service orchestrating maintenance logging, component swaps, and wear adjustments."""

    @staticmethod
    def _calculate_component_status(current_wear: Decimal, lifespan: Decimal) -> ComponentStatus:
        """Derive standard component wear status from wear points ratio."""
        if current_wear <= Decimal("0.00"):
            return ComponentStatus.NEW
        if lifespan <= Decimal("0.00"):
            return ComponentStatus.REPLACE_RECOMMENDED

        pct = (float(current_wear) / float(lifespan)) * 100.0
        if pct < 75.0:
            return ComponentStatus.OPTIMAL
        if pct < 90.0:
            return ComponentStatus.ATTENTION_NEEDED
        return ComponentStatus.REPLACE_RECOMMENDED

    async def record_maintenance(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        component_id: uuid.UUID,
        log_type: MaintenanceType,
        description: str | None = None,
        cost: Decimal | float | int | None = None,
        odometer_km: Decimal | float | int | None = None,
        performed_at: datetime | None = None,
    ) -> tuple[Component, MaintenanceLog]:
        """Create and persist an individual maintenance log entry."""
        stmt = (
            select(Component)
            .where(Component.id == component_id)
            .options(selectinload(Component.bike))
        )
        comp = (await session.execute(stmt)).scalar_one_or_none()
        if not comp or not comp.bike:
            raise EntityNotFoundError(f"Component {component_id} not found")

        if comp.bike.user_id != user_id:
            raise PermissionDeniedError("Component belongs to a bike owned by another user")

        if odometer_km is not None:
            odo = Decimal(str(odometer_km))
        else:
            odo = Decimal(str(round(comp.bike.total_distance_m / 1000.0, 2)))

        cost_val = Decimal(str(cost)) if cost is not None else Decimal("0.00")
        log_date = performed_at or datetime.now(UTC)

        log = MaintenanceLog(
            user_id=user_id,
            component_id=comp.id,
            log_type=log_type,
            description=description,
            cost=cost_val,
            odometer_km=odo,
            performed_at=log_date,
        )
        session.add(log)
        await session.flush()

        logger.info(
            "Recorded maintenance log %s (%s) for component %s",
            log.id,
            log_type.value,
            component_id,
        )
        return comp, log

    async def replace_component(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        component_id: uuid.UUID,
        new_brand_model: str | None = None,
        new_lifespan_wear_points: Decimal | float | int | None = None,
        cost: Decimal | float | int | None = None,
        description: str | None = None,
        performed_at: datetime | None = None,
        odometer_km: Decimal | float | int | None = None,
    ) -> tuple[Component, Component, MaintenanceLog]:
        """Execute full component replacement workflow.

        1. Retires existing component, archiving status and timestamp.
        2. Provisions new component with fresh zero-wear baseline.
        3. Persists audit MaintenanceLog documenting component swap.
        """
        stmt = (
            select(Component)
            .where(Component.id == component_id)
            .options(selectinload(Component.bike))
        )
        old_comp = (await session.execute(stmt)).scalar_one_or_none()
        if not old_comp or not old_comp.bike:
            raise EntityNotFoundError(f"Component {component_id} not found")

        if old_comp.bike.user_id != user_id:
            raise PermissionDeniedError("Component belongs to a bike owned by another user")

        if old_comp.retired_at is not None or old_comp.status == ComponentStatus.RETIRED:
            raise ComponentAlreadyRetiredError(f"Component {component_id} is already retired")

        event_time = performed_at or datetime.now(UTC)
        cost_val = Decimal(str(cost)) if cost is not None else Decimal("0.00")

        if odometer_km is not None:
            odo = Decimal(str(odometer_km))
        else:
            odo = Decimal(str(round(old_comp.bike.total_distance_m / 1000.0, 2)))

        # 1. Archive previous component
        old_comp.status = ComponentStatus.RETIRED
        old_comp.retired_at = event_time

        # 2. Provision new replacement component
        lifespan_val = (
            Decimal(str(new_lifespan_wear_points))
            if new_lifespan_wear_points is not None
            else old_comp.lifespan_wear_points
        )
        brand_val = new_brand_model.strip() if new_brand_model else old_comp.brand_model

        new_comp = Component(
            bike_id=old_comp.bike_id,
            component_type=old_comp.component_type,
            brand_model=brand_val,
            lifespan_wear_points=lifespan_val,
            current_wear_points=Decimal("0.00"),
            status=ComponentStatus.NEW,
            installed_at=event_time,
            retired_at=None,
        )
        session.add(new_comp)
        await session.flush()

        # 3. Record replacement log linking to new component
        desc = (
            description
            or f"Replaced {old_comp.brand_model} with {new_comp.brand_model}. "
            f"Previous mileage was {old_comp.current_wear_points:.1f} WP."
        )
        log = MaintenanceLog(
            user_id=user_id,
            component_id=new_comp.id,
            log_type=MaintenanceType.REPLACE,
            description=desc,
            cost=cost_val,
            odometer_km=odo,
            performed_at=event_time,
        )
        session.add(log)

        # 4. If chain, automatically record fresh factory lubrication entry
        if new_comp.component_type == ComponentType.CHAIN:
            chain_lube_log = MaintenanceLog(
                user_id=user_id,
                component_id=new_comp.id,
                log_type=MaintenanceType.CLEAN_AND_LUBE,
                description="New chain factory lubrication baseline",
                cost=Decimal("0.00"),
                odometer_km=odo,
                performed_at=event_time,
            )
            session.add(chain_lube_log)

        await session.flush()

        logger.info(
            "Retired component %s and installed replacement %s for bike %s",
            old_comp.id,
            new_comp.id,
            old_comp.bike_id,
        )
        return old_comp, new_comp, log

    async def get_bike_maintenance_history(
        self,
        session: AsyncSession,
        bike_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        log_type: MaintenanceType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> BikeMaintenanceHistory:
        """Retrieve aggregated maintenance timeline and statistics for a bicycle."""
        bike_stmt = select(Bike).where(Bike.id == bike_id)
        bike = (await session.execute(bike_stmt)).scalar_one_or_none()
        if not bike:
            raise EntityNotFoundError(f"Bike {bike_id} not found")

        if user_id is not None and bike.user_id != user_id:
            raise PermissionDeniedError("Bike belongs to another athlete")

        # Base query joining components to include active and retired parts
        base_query = (
            select(MaintenanceLog, Component)
            .join(Component, MaintenanceLog.component_id == Component.id)
            .where(Component.bike_id == bike_id)
        )
        if log_type:
            base_query = base_query.where(MaintenanceLog.log_type == log_type)

        # Compute aggregates
        stats_query = (
            select(
                func.coalesce(func.sum(MaintenanceLog.cost), Decimal("0.00")),
                func.count(MaintenanceLog.id),
            )
            .join(Component, MaintenanceLog.component_id == Component.id)
            .where(Component.bike_id == bike_id)
        )
        if log_type:
            stats_query = stats_query.where(MaintenanceLog.log_type == log_type)

        stats_res = await session.execute(stats_query)
        total_cost_val, total_events_val = stats_res.one()
        total_cost = Decimal(str(total_cost_val)) if total_cost_val is not None else Decimal("0.00")
        total_events = int(total_events_val or 0)

        # Query paginated log list
        ordered_query = (
            base_query.order_by(
                MaintenanceLog.performed_at.desc(),
                MaintenanceLog.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = (await session.execute(ordered_query)).all()

        log_entries: list[MaintenanceLogEntry] = []
        for log_item, comp_item in rows:
            log_entries.append(
                MaintenanceLogEntry(
                    id=log_item.id,
                    component_id=comp_item.id,
                    component_type=comp_item.component_type,
                    brand_model=comp_item.brand_model,
                    user_id=log_item.user_id,
                    log_type=log_item.log_type,
                    description=log_item.description,
                    cost=log_item.cost or Decimal("0.00"),
                    odometer_km=log_item.odometer_km,
                    performed_at=log_item.performed_at,
                    created_at=log_item.created_at,
                )
            )

        total_distance_km = Decimal(str(round(bike.total_distance_m / 1000.0, 2)))

        return BikeMaintenanceHistory(
            bike_id=bike.id,
            bike_name=bike.name,
            total_distance_km=total_distance_km,
            total_cost=total_cost,
            total_events=total_events,
            logs=log_entries,
        )

    async def adjust_wear_points(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        component_id: uuid.UUID,
        new_wear_points: Decimal | float | int,
        reason: str | None = None,
        performed_at: datetime | None = None,
    ) -> tuple[Component, MaintenanceLog]:
        """Manually adjust wear points and recalibrate component status."""
        stmt = (
            select(Component)
            .where(Component.id == component_id)
            .options(selectinload(Component.bike))
        )
        comp = (await session.execute(stmt)).scalar_one_or_none()
        if not comp or not comp.bike:
            raise EntityNotFoundError(f"Component {component_id} not found")

        if comp.bike.user_id != user_id:
            raise PermissionDeniedError("Component belongs to a bike owned by another user")

        if comp.retired_at is not None or comp.status == ComponentStatus.RETIRED:
            raise ComponentAlreadyRetiredError(f"Component {component_id} is retired")

        old_wear = comp.current_wear_points
        wear_val = max(Decimal("0.00"), Decimal(str(new_wear_points)))

        comp.current_wear_points = wear_val
        comp.status = self._calculate_component_status(wear_val, comp.lifespan_wear_points)

        now = performed_at or datetime.now(UTC)
        odo = Decimal(str(round(comp.bike.total_distance_m / 1000.0, 2)))

        desc = f"Manual wear recalibration from {old_wear:.1f} to {wear_val:.1f} WP."
        if reason:
            desc += f" Reason: {reason}"

        log = MaintenanceLog(
            user_id=user_id,
            component_id=comp.id,
            log_type=MaintenanceType.INSPECT_TUNE,
            description=desc,
            cost=Decimal("0.00"),
            odometer_km=odo,
            performed_at=now,
        )
        session.add(log)
        await session.flush()

        logger.info(
            "Recalibrated wear on component %s: %s -> %s WP (status: %s)",
            comp.id,
            old_wear,
            wear_val,
            comp.status.value,
        )
        return comp, log
