"""Strava webhook verification handshake and high-speed ingestion service."""

import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from velopulse.core.config import Settings, get_settings
from velopulse.domain.strava import (
    StravaWebhookChallenge,
    StravaWebhookChallengeResponse,
    StravaWebhookEvent,
)

from velopulse.tasks.activities import ingest_activity_task

logger = logging.getLogger("velopulse.strava.webhook")


class StravaWebhookService:
    """Handles Strava webhook verification challenges and async queue ingestion."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def process_challenge(
        self,
        challenge: StravaWebhookChallenge,
    ) -> StravaWebhookChallengeResponse:
        """Validate Strava subscription verification handshake.

        Must respond with HTTP 200 and the hub.challenge in under 2 seconds.
        """
        if challenge.hub_mode != "subscribe":
            logger.warning("Rejected webhook challenge: invalid hub.mode '%s'", challenge.hub_mode)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported hub.mode: {challenge.hub_mode}",
            )

        if challenge.hub_verify_token != self.settings.STRAVA_VERIFY_TOKEN:
            logger.warning(
                "Rejected webhook challenge: token mismatch. Provided: %s",
                challenge.hub_verify_token,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Verification token mismatch",
            )

        logger.info("Strava webhook challenge verified successfully")
        return StravaWebhookChallengeResponse(hub_challenge=challenge.hub_challenge)

    async def enqueue_event(
        self,
        event: StravaWebhookEvent,
        redis_client: aioredis.Redis,
    ) -> None:
        """Enqueue event for background ingestion via Taskiq (<50ms SLA)."""
        logger.info(
            "Ingesting Strava event: object=%s, id=%s, aspect=%s, owner=%s",
            event.object_type,
            event.object_id,
            event.aspect_type,
            event.owner_id,
        )
        if event.object_type == "activity" and event.aspect_type == "create":
            try:
                await ingest_activity_task.kiq(event.owner_id, event.object_id)
            except Exception as exc:
                logger.error("Failed to enqueue webhook event via Taskiq: %s", exc)
                # Re-raise so FastAPI surfaces transient internal error if broker unreachable
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to enqueue webhook event",
                ) from exc

