"""Component wear calculation tasks for Taskiq background workers."""

import importlib
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select

from velopulse.core.config import get_settings
from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import ComponentStatus
from velopulse.db.models.wear import ActivityComponentWear
from velopulse.db.session import get_session_context
from velopulse.services.wear.service import WearCalculationService
from velopulse.tasks.broker import broker

logger = logging.getLogger("velopulse.tasks.wear")
settings = get_settings()


@broker.task(max_retries=3)
async def calculate_wear_task(activity_id: str | uuid.UUID) -> None:
    """Calculate physics-based component wear for an activity and update state machine."""
    act_uuid = uuid.UUID(str(activity_id)) if isinstance(activity_id, str) else activity_id
    logger.info("Starting wear calculation for activity %s", act_uuid)

    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    lock_name = f"lock:calculate_wear:{act_uuid}"

    async with redis_client.lock(lock_name, timeout=60, blocking_timeout=2):
        try:
            async with get_session_context() as session:
                # 1. Fetch Activity
                stmt = select(Activity).where(Activity.id == act_uuid)
                result = await session.execute(stmt)
                activity = result.scalar_one_or_none()

                if not activity:
                    logger.warning("Activity %s not found for wear calculation", act_uuid)
                    return

                if not activity.bike_id:
                    logger.info("Activity %s has no bike assigned. Skipping wear calculation.", act_uuid)
                    return

                # 2. Idempotency Check: verify if wear attributions already exist
                check_stmt = select(ActivityComponentWear).where(
                    ActivityComponentWear.activity_id == act_uuid
                )
                existing = await session.execute(check_stmt)
                if existing.first() is not None:
                    logger.info("Wear attribution records already exist for activity %s. Skipping.", act_uuid)
                    return

                # 3. Fetch Bike and Active Components
                bike_stmt = select(Bike).where(Bike.id == activity.bike_id)
                bike_res = await session.execute(bike_stmt)
                bike = bike_res.scalar_one_or_none()

                if not bike:
                    logger.warning("Bike %s not found for activity %s", activity.bike_id, act_uuid)
                    return

                comp_stmt = select(Component).where(
                    Component.bike_id == activity.bike_id,
                    Component.retired_at.is_(None),
                )
                comp_res = await session.execute(comp_stmt)
                components = list(comp_res.scalars().all())

                if not components:
                    logger.info("No active components installed on bike %s.", bike.id)
                    return

                # 4. Execute Physics Calculation
                service = WearCalculationService()
                calc_result = service.calculate_activity_wear(
                    activity=activity,
                    components=components,
                    bike_type=bike.bike_type,
                )

                # 5. Persist Wear Attributions and Update Components
                comp_map = {c.id: c for c in components}
                for delta in calc_result.component_wear_records:
                    attribution = ActivityComponentWear(
                        activity_id=act_uuid,
                        component_id=delta.component_id,
                        wear_delta=Decimal(str(delta.wear_delta)),
                        base_distance_km=Decimal(str(calc_result.distance_km)),
                        elevation_factor=Decimal(str(calc_result.elevation_factor)),
                        weather_factor=Decimal(str(calc_result.weather_multiplier)),
                    )
                    session.add(attribution)

                    comp = comp_map.get(delta.component_id)
                    if comp:
                        comp.current_wear_points = Decimal(str(delta.new_wear_points))
                        comp.status = delta.new_status
                        if delta.new_status == ComponentStatus.RETIRED and comp.retired_at is None:
                            comp.retired_at = datetime.now(UTC)

                # 6. Update Cumulative Bike Statistics
                bike.total_distance_m += int(activity.distance_m) if activity.distance_m else 0
                bike.total_elevation_m += (
                    int(activity.total_elevation_m) if activity.total_elevation_m else 0
                )

                await session.commit()

                logger.info(
                    "Wear calculation complete for activity %s (%d components updated, Ef=%.2f, Wm=%.2f)",
                    act_uuid,
                    len(calc_result.component_wear_records),
                    calc_result.elevation_factor,
                    calc_result.weather_multiplier,
                )

                # 7. Pipeline Handoff: Trigger Sprint 07 Notification Dispatcher if thresholds exceeded
                if calc_result.thresholds_exceeded:
                    logger.warning(
                        "Activity %s caused %d component(s) to cross critical maintenance thresholds",
                        act_uuid,
                        len(calc_result.thresholds_exceeded),
                    )
                    try:
                        notify_mod = importlib.import_module("velopulse.tasks.notifications")
                        dispatch_notifications_task = notify_mod.dispatch_notifications_task
                        await dispatch_notifications_task.kiq(str(act_uuid))
                        logger.info("Enqueued dispatch_notifications_task for activity %s", act_uuid)
                    except (ImportError, AttributeError):
                        logger.debug(
                            "dispatch_notifications_task is not yet registered (Sprint 07 deliverable)"
                        )

        finally:
            await redis_client.aclose()
