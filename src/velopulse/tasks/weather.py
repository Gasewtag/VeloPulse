"""Weather telemetry enrichment tasks for Taskiq background workers."""

import logging
import uuid

from redis.asyncio import Redis
from sqlalchemy import select

from velopulse.core.config import get_settings
from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.session import get_session_context
from velopulse.services.weather.service import WeatherEnrichmentService
from velopulse.tasks.broker import broker

logger = logging.getLogger("velopulse.tasks.weather")
settings = get_settings()


@broker.task(max_retries=3)
async def enrich_weather_task(activity_id: str | uuid.UUID) -> None:
    """Enrich an ingested Activity with historical weather observations and Wm factor."""
    act_uuid = uuid.UUID(str(activity_id)) if isinstance(activity_id, str) else activity_id
    logger.info("Starting weather enrichment for activity %s", act_uuid)

    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    lock_name = f"lock:enrich_weather:{act_uuid}"

    async with redis_client.lock(lock_name, timeout=60, blocking_timeout=2):
        try:
            async with get_session_context() as session:
                # 1. Fetch Activity
                stmt = select(Activity).where(Activity.id == act_uuid)
                result = await session.execute(stmt)
                activity = result.scalar_one_or_none()

                if not activity:
                    logger.warning("Activity %s not found for weather enrichment", act_uuid)
                    return

                # 2. Check Idempotency
                if activity.is_weather_enriched and activity.weather_data:
                    logger.info("Activity %s is already weather-enriched. Skipping.", act_uuid)
                    return

                # 3. Resolve Bike Type if linked
                bike_type_val: str | None = None
                if activity.bike_id:
                    bike_stmt = select(Bike).where(Bike.id == activity.bike_id)
                    bike_res = await session.execute(bike_stmt)
                    bike = bike_res.scalar_one_or_none()
                    if bike:
                        bike_type_val = (
                            bike.bike_type.value
                            if hasattr(bike.bike_type, "value")
                            else str(bike.bike_type)
                        )

                # 4. Compute Environmental Weather Telemetry
                service = WeatherEnrichmentService(settings=settings)
                weather_result = await service.enrich_activity_weather(
                    start_latitude=activity.start_latitude,
                    start_longitude=activity.start_longitude,
                    start_time=activity.start_time,
                    moving_time_s=activity.moving_time_s,
                    bike_type=bike_type_val,
                )

                # 5. Persist Enriched Telemetry to PostgreSQL
                activity.weather_data = weather_result.model_dump(mode="json")
                activity.is_weather_enriched = True
                await session.commit()

                logger.info(
                    "Activity %s successfully enriched: condition=%s, Wm=%.2f, precip=%.1fmm",
                    act_uuid,
                    weather_result.surface_condition,
                    weather_result.weather_multiplier,
                    weather_result.total_precipitation_mm,
                )

                # 6. Pipeline Handoff: Trigger Sprint 06 Wear Calculation
                try:
                    import importlib

                    wear_mod = importlib.import_module("velopulse.tasks.wear")
                    calculate_wear_task = wear_mod.calculate_wear_task
                    await calculate_wear_task.kiq(str(act_uuid))
                    logger.info("Enqueued calculate_wear_task for activity %s", act_uuid)
                except (ImportError, AttributeError):
                    logger.debug(
                        "calculate_wear_task is not yet registered (Sprint 06 deliverable)"
                    )


        finally:
            await redis_client.aclose()
