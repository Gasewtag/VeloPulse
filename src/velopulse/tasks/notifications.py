"""Notification dispatch tasks for Taskiq background workers."""

import logging
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from velopulse.core.config import get_settings
from velopulse.db.models.activity import Activity
from velopulse.db.models.bike import Bike
from velopulse.db.models.component import Component
from velopulse.db.models.enums import ComponentStatus
from velopulse.db.session import get_session_context
from velopulse.services.notifications.dispatcher import NotificationDispatcher
from velopulse.tasks.broker import broker

logger = logging.getLogger("velopulse.tasks.notifications")
settings = get_settings()


@broker.task(max_retries=3)
async def dispatch_notifications_task(activity_id: str | uuid.UUID) -> None:
    """Evaluate activity degradation and dispatch Telegram alerts if thresholds were crossed."""
    act_uuid = uuid.UUID(str(activity_id)) if isinstance(activity_id, str) else activity_id
    logger.info("Evaluating notification dispatch for activity %s", act_uuid)

    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    lock_name = f"lock:dispatch_notifications:{act_uuid}"

    async with redis_client.lock(lock_name, timeout=60, blocking_timeout=2):
        try:
            async with get_session_context() as session:
                # 1. Fetch Activity with Bike and User
                stmt = (
                    select(Activity)
                    .where(Activity.id == act_uuid)
                    .options(
                        selectinload(Activity.bike).selectinload(Bike.user),
                        selectinload(Activity.bike).selectinload(Bike.components),
                    )
                )
                res = await session.execute(stmt)
                activity = res.scalar_one_or_none()

                if not activity or not activity.bike or not activity.bike.user:
                    logger.info(
                        "Activity, bike, or user not found for %s. Skipping notifications.",
                        act_uuid,
                    )
                    return

                bike = activity.bike
                user = bike.user

                if not user.telegram_chat_id:
                    logger.info(
                        "User %s has no Telegram chat ID linked. Skipping dispatch.", user.id
                    )
                    return

                # 2. Filter components requiring maintenance
                critical_components: list[Component] = [
                    comp
                    for comp in bike.components
                    if comp.retired_at is None
                    and comp.status
                    in (
                        ComponentStatus.ATTENTION_NEEDED,
                        ComponentStatus.REPLACE_RECOMMENDED,
                        ComponentStatus.RETIRED,
                    )
                ]

                if not critical_components:
                    logger.info("No components in critical status for bike %s.", bike.id)
                    return

                # 3. Dispatch alert via NotificationDispatcher
                dispatcher = NotificationDispatcher(settings=settings)
                try:
                    await dispatcher.dispatch_wear_alert(
                        user=user,
                        bike=bike,
                        activity=activity,
                        components_to_alert=critical_components,
                    )
                finally:
                    await dispatcher.close()

        finally:
            await redis_client.aclose()
