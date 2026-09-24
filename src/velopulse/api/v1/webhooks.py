"""Strava webhook verification handshake and real-time push event ingestion."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Response, status

from velopulse.core.config import get_settings
from velopulse.domain.strava import (
    StravaWebhookChallenge,
    StravaWebhookChallengeResponse,
    StravaWebhookEvent,
)
from velopulse.services.strava.webhook import StravaWebhookService

logger = logging.getLogger("velopulse.api.webhooks")

router = APIRouter()
settings = get_settings()


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Dependency yielding an async Redis client from the connection pool."""
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def get_webhook_service() -> StravaWebhookService:
    """Dependency injector for StravaWebhookService."""
    return StravaWebhookService(settings=settings)


@router.get(
    "/strava",
    summary="Strava webhook subscription challenge handshake",
    response_model=StravaWebhookChallengeResponse,
)
async def strava_webhook_challenge(
    hub_mode: Annotated[str, Query(alias="hub.mode", description="Subscription mode")],
    hub_challenge: Annotated[
        str, Query(alias="hub.challenge", description="Challenge token to echo back")
    ],
    hub_verify_token: Annotated[
        str, Query(alias="hub.verify_token", description="Verification token")
    ],
    webhook_service: StravaWebhookService = Depends(get_webhook_service),
) -> StravaWebhookChallengeResponse:
    """Validate Strava subscription verification handshake (<50ms response)."""
    challenge = StravaWebhookChallenge.model_validate(
        {
            "hub.mode": hub_mode,
            "hub.challenge": hub_challenge,
            "hub.verify_token": hub_verify_token,
        }
    )
    return webhook_service.process_challenge(challenge)


@router.post(
    "/strava",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ingest Strava real-time event notification",
    response_class=Response,
)
async def strava_webhook_event(
    event: StravaWebhookEvent,
    redis_client: aioredis.Redis = Depends(get_redis),
    webhook_service: StravaWebhookService = Depends(get_webhook_service),
) -> Response:
    """Receive Strava webhook event and enqueue to Redis immediately (<50ms SLA)."""
    await webhook_service.enqueue_event(event=event, redis_client=redis_client)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
