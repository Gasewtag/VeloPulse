"""Bicycle maintenance and historical audit trail endpoints."""

import logging
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.models.bike import Bike
from velopulse.db.models.enums import MaintenanceType
from velopulse.db.session import get_db_session
from velopulse.schemas.maintenance import (
    BikeMaintenanceHistoryResponse,
    CreateMaintenanceLogRequest,
    MaintenanceLogResponse,
    ReplaceComponentRequest,
)
from velopulse.services.maintenance import (
    ComponentAlreadyRetiredError,
    EntityNotFoundError,
    MaintenanceError,
    MaintenanceService,
    PermissionDeniedError,
)

logger = logging.getLogger("velopulse.api.bikes")

router = APIRouter()


def get_maintenance_service() -> MaintenanceService:
    """Dependency injector for MaintenanceService."""
    return MaintenanceService()


@router.get(
    "/{bike_id}/maintenance",
    summary="Retrieve bicycle maintenance timeline and historical audit trail",
    response_model=BikeMaintenanceHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_bike_maintenance_history(
    bike_id: uuid.UUID,
    log_type: Annotated[
        MaintenanceType | None,
        Query(description="Filter events by maintenance action type"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Maximum number of log events to return"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Pagination offset for log records"),
    ] = 0,
    db: AsyncSession = Depends(get_db_session),
    service: MaintenanceService = Depends(get_maintenance_service),
) -> BikeMaintenanceHistoryResponse:
    """Return comprehensive maintenance timeline with accumulated odometer and cost tracking."""
    try:
        history = await service.get_bike_maintenance_history(
            session=db,
            bike_id=bike_id,
            log_type=log_type,
            limit=limit,
            offset=offset,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return BikeMaintenanceHistoryResponse(
        bike_id=history.bike_id,
        bike_name=history.bike_name,
        total_distance_km=history.total_distance_km,
        total_cost=history.total_cost,
        total_events=history.total_events,
        items=[
            MaintenanceLogResponse(
                id=log.id,
                component_id=log.component_id,
                component_type=log.component_type,
                brand_model=log.brand_model,
                log_type=log.log_type,
                description=log.description,
                cost=log.cost,
                odometer_km=log.odometer_km,
                performed_at=log.performed_at,
                created_at=log.created_at,
            )
            for log in history.logs
        ],
    )


@router.post(
    "/{bike_id}/maintenance",
    summary="Record maintenance event on a bicycle component",
    response_model=MaintenanceLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_bike_maintenance(
    bike_id: uuid.UUID,
    payload: CreateMaintenanceLogRequest,
    db: AsyncSession = Depends(get_db_session),
    service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceLogResponse:
    """Record a service, inspection, repair, or lubrication log entry."""
    bike_stmt = select(Bike).where(Bike.id == bike_id)
    bike = (await db.execute(bike_stmt)).scalar_one_or_none()
    if not bike:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bike {bike_id} not found",
        )

    try:
        comp, log = await service.record_maintenance(
            session=db,
            user_id=bike.user_id,
            component_id=payload.component_id,
            log_type=payload.log_type,
            description=payload.description,
            cost=payload.cost,
            odometer_km=payload.odometer_km,
            performed_at=payload.performed_at,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except MaintenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MaintenanceLogResponse(
        id=log.id,
        component_id=comp.id,
        component_type=comp.component_type,
        brand_model=comp.brand_model,
        log_type=log.log_type,
        description=log.description,
        cost=log.cost or Decimal("0.00"),
        odometer_km=log.odometer_km,
        performed_at=log.performed_at,
        created_at=log.created_at,
    )


@router.post(
    "/{bike_id}/replace",
    summary="Replace bicycle component, retiring old and initializing new",
    response_model=MaintenanceLogResponse,
    status_code=status.HTTP_200_OK,
)
async def replace_bike_component(
    bike_id: uuid.UUID,
    payload: ReplaceComponentRequest,
    db: AsyncSession = Depends(get_db_session),
    service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceLogResponse:
    """Retire component, provision new component with 0 WP wear, and log event."""
    bike_stmt = select(Bike).where(Bike.id == bike_id)
    bike = (await db.execute(bike_stmt)).scalar_one_or_none()
    if not bike:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bike {bike_id} not found",
        )

    try:
        _old_comp, new_comp, log = await service.replace_component(
            session=db,
            user_id=bike.user_id,
            component_id=payload.component_id,
            new_brand_model=payload.new_brand_model,
            new_lifespan_wear_points=payload.new_lifespan_wear_points,
            cost=payload.cost,
            description=payload.description,
            odometer_km=payload.odometer_km,
            performed_at=payload.performed_at,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ComponentAlreadyRetiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return MaintenanceLogResponse(
        id=log.id,
        component_id=new_comp.id,
        component_type=new_comp.component_type,
        brand_model=new_comp.brand_model,
        log_type=log.log_type,
        description=log.description,
        cost=log.cost or Decimal("0.00"),
        odometer_km=log.odometer_km,
        performed_at=log.performed_at,
        created_at=log.created_at,
    )
