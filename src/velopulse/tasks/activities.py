"""Activity ingestion and processing tasks."""

import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select

from velopulse.core.config import get_settings
from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.models.user import User
from velopulse.db.session import get_session_context
from velopulse.services.strava.auth import StravaAuthService
from velopulse.services.strava.client import StravaAPIError, StravaClient
from velopulse.tasks.broker import broker

logger = logging.getLogger("velopulse.tasks.activities")

settings = get_settings()


@broker.task(max_retries=3)
async def ingest_activity_task(strava_athlete_id: int, strava_activity_id: int) -> None:
    """Consume webhook payload and ingest the Strava activity into the database."""
    logger.info(
        f"Starting ingestion for activity {strava_activity_id} (athlete {strava_athlete_id})"
    )

    # We use a separate redis connection for locking
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    lock_name = f"lock:ingest_activity:{strava_activity_id}"

    # Try to acquire lock
    async with redis_client.lock(lock_name, timeout=60, blocking_timeout=2):
        try:
            async with get_session_context() as session:
                # 1. Check if activity already exists
                activity_result = await session.execute(
                    select(Activity).where(Activity.strava_activity_id == strava_activity_id)
                )
                if activity_result.scalar_one_or_none() is not None:
                    logger.info(
                        f"Activity {strava_activity_id} already exists. Skipping duplicate."
                    )
                    return

                # 2. Get User
                user_result = await session.execute(
                    select(User).where(User.strava_athlete_id == strava_athlete_id)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    logger.warning(
                        f"Athlete {strava_athlete_id} not found in database. Cannot ingest activity {strava_activity_id}."
                    )
                    return

                # 3. Get valid access token
                auth_service = StravaAuthService()
                access_token = await auth_service.get_valid_access_token(user, session)

                # 4. Fetch activity from Strava API
                client = StravaClient()
                try:
                    detailed_activity = await client.get_activity(access_token, strava_activity_id)
                except StravaAPIError as e:
                    if e.status_code and e.status_code in [429, 500, 502, 503, 504]:
                        logger.warning(
                            f"Transient error fetching activity {strava_activity_id}: {e}"
                        )
                        raise  # Raise to trigger retry
                    else:
                        logger.error(
                            f"Unrecoverable error fetching activity {strava_activity_id}: {e}"
                        )
                        # Could send to a DLQ here
                        return

                # 5. Resolve Bike
                bike_id = None
                if detailed_activity.gear_id:
                    result = await session.execute(
                        select(Bike).where(Bike.strava_gear_id == detailed_activity.gear_id)
                    )
                    bike = result.scalar_one_or_none()
                    if bike:
                        bike_id = bike.id

                # 6. Persist Activity
                start_lat = None
                start_lng = None
                if detailed_activity.start_latlng and len(detailed_activity.start_latlng) == 2:
                    start_lat = detailed_activity.start_latlng[0]
                    start_lng = detailed_activity.start_latlng[1]

                new_activity = Activity(
                    user_id=user.id,
                    bike_id=bike_id,
                    strava_activity_id=detailed_activity.id,
                    name=detailed_activity.name,
                    activity_type=detailed_activity.type,
                    distance_m=detailed_activity.distance,
                    moving_time_s=detailed_activity.moving_time,
                    total_elevation_m=detailed_activity.total_elevation_gain,
                    start_latitude=start_lat,
                    start_longitude=start_lng,
                    start_time=detailed_activity.start_date,
                    created_at=datetime.now(UTC),
                )
                session.add(new_activity)
                await session.commit()
                logger.info(f"Successfully ingested activity {strava_activity_id}")

                # 7. Enqueue weather telemetry enrichment
                try:
                    from velopulse.tasks.weather import enrich_weather_task
                    await enrich_weather_task.kiq(str(new_activity.id))
                    logger.info(f"Enqueued enrich_weather_task for activity {new_activity.id}")
                except Exception as exc:
                    logger.error(f"Failed to enqueue enrich_weather_task for activity {new_activity.id}: {exc}")


        finally:
            await redis_client.aclose()
