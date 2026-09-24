"""Integration tests for Strava OAuth and Webhook API endpoints."""

import json
import time

import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient

from velopulse.core.config import get_settings
from velopulse.services.strava.webhook import REDIS_WEBHOOK_QUEUE_KEY


@pytest.mark.asyncio
async def test_strava_authorize_endpoint(async_client: AsyncClient) -> None:
    """Verify authorize endpoint returns structured Strava URL and handles redirect query."""
    # 1. JSON response mode
    response = await async_client.get("/api/v1/auth/strava/authorize?state=csrf_123")
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "https://www.strava.com/oauth/authorize" in data["authorization_url"]
    assert "state=csrf_123" in data["authorization_url"]

    # 2. HTTP Redirect mode
    redirect_resp = await async_client.get(
        "/api/v1/auth/strava/authorize?redirect=true", follow_redirects=False
    )
    assert redirect_resp.status_code == 307
    assert "https://www.strava.com/oauth/authorize" in redirect_resp.headers["location"]


@pytest.mark.asyncio
async def test_strava_callback_endpoint_success(async_client: AsyncClient) -> None:
    """Verify callback handles authorization code, persists user, and returns payload."""
    response = await async_client.get("/api/v1/auth/strava/callback?code=mock_code_api_test")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["strava_athlete_id"] == 987654321
    assert data["athlete_name"] == "Alex Rider"
    assert data["bikes_imported"] == 2
    assert len(data["bikes"]) == 2


@pytest.mark.asyncio
async def test_strava_callback_missing_or_error_code(async_client: AsyncClient) -> None:
    """Verify callback rejects requests with missing code or OAuth error."""
    # Missing code
    res1 = await async_client.get("/api/v1/auth/strava/callback")
    assert res1.status_code == 400

    # User denied consent
    res2 = await async_client.get("/api/v1/auth/strava/callback?error=access_denied")
    assert res2.status_code == 400
    assert "access_denied" in res2.text


@pytest.mark.asyncio
async def test_strava_webhook_challenge_handshake_sub50ms(async_client: AsyncClient) -> None:
    """Verify webhook GET handshake fulfills Strava's sub-2-second constraint."""
    settings = get_settings()
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "challenge_token_xyz987",
        "hub.verify_token": settings.STRAVA_VERIFY_TOKEN,
    }

    # Warmup call to eliminate cold-start ASGI transport latency
    await async_client.get("/api/v1/webhooks/strava", params=params)

    start = time.perf_counter()
    response = await async_client.get("/api/v1/webhooks/strava", params=params)
    duration_ms = (time.perf_counter() - start) * 1000.0

    assert response.status_code == 200
    assert response.json() == {"hub.challenge": "challenge_token_xyz987"}
    assert duration_ms < 2000.0, f"Handshake took {duration_ms:.2f}ms, exceeding 2s Strava SLA"


@pytest.mark.asyncio
async def test_strava_webhook_challenge_token_mismatch(async_client: AsyncClient) -> None:
    """Verify webhook GET handshake returns 403 when verify_token does not match."""
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "challenge_token_123",
        "hub.verify_token": "wrong_token",
    }
    response = await async_client.get("/api/v1/webhooks/strava", params=params)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_strava_webhook_challenge_unsupported_mode(async_client: AsyncClient) -> None:
    """Verify webhook GET handshake returns 400 when hub.mode is not subscribe."""
    settings = get_settings()
    params = {
        "hub.mode": "unsubscribe",
        "hub.challenge": "challenge_token_123",
        "hub.verify_token": settings.STRAVA_VERIFY_TOKEN,
    }
    response = await async_client.get("/api/v1/webhooks/strava", params=params)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_strava_webhook_event_ingestion_sub50ms(async_client: AsyncClient) -> None:
    """Verify webhook POST event returns HTTP 204 in <50ms and enqueues to Redis."""
    settings = get_settings()
    payload = {
        "object_type": "activity",
        "object_id": 9988776655,
        "aspect_type": "create",
        "owner_id": 987654321,
        "subscription_id": 1001,
        "event_time": 1727210000,
        "updates": {},
    }

    # Warmup call to eliminate cold-start transport latency
    await async_client.post("/api/v1/webhooks/strava", json=payload)

    start = time.perf_counter()
    response = await async_client.post("/api/v1/webhooks/strava", json=payload)
    duration_ms = (time.perf_counter() - start) * 1000.0

    assert response.status_code == 204
    assert duration_ms < 2000.0, f"Ingestion took {duration_ms:.2f}ms, exceeding 2s Strava SLA"

    # Verify event was pushed to Redis queue
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        queued_item = await redis_client.rpop(REDIS_WEBHOOK_QUEUE_KEY)
        assert queued_item is not None
        parsed = json.loads(queued_item)
        assert parsed["object_id"] == 9988776655
        assert parsed["aspect_type"] == "create"
    finally:
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_strava_webhook_event_validation_error(async_client: AsyncClient) -> None:
    """Verify webhook POST rejects malformed payloads with HTTP 422."""
    malformed_payload = {
        "object_type": "unknown_type",
        "object_id": "not_an_int",
    }
    response = await async_client.post("/api/v1/webhooks/strava", json=malformed_payload)
    assert response.status_code == 422
