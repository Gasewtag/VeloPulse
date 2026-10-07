"""Unit and integration tests for Prometheus metrics and telemetry."""

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from velopulse.observability.metrics import (
    SYSTEM_HEALTH_STATUS,
    TASK_EXECUTIONS_TOTAL,
    TASK_PROCESSING_DURATION_SECONDS,
    TASK_QUEUE_BACKLOG,
    WEAR_CALCULATION_DURATION_SECONDS,
    WEATHER_ENRICHMENT_DURATION_SECONDS,
    get_metrics_payload,
    update_queue_backlog_metrics,
)


@pytest.mark.asyncio
async def test_metrics_endpoint_exposition(async_client: AsyncClient) -> None:
    """Verify that the /metrics endpoint returns HTTP 200 with Prometheus text data."""
    # Issue a health request first to trigger request metrics
    health_resp = await async_client.get("/health")
    assert health_resp.status_code == 200

    response = await async_client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")

    body = response.text
    assert "velopulse_http_requests_total" in body
    assert "velopulse_system_health_status" in body
    assert "velopulse_task_queue_backlog" in body


@pytest.mark.asyncio
async def test_update_queue_backlog_metrics() -> None:
    """Verify that update_queue_backlog_metrics queries Redis and sets gauges."""
    mock_redis = AsyncMock()
    mock_redis.llen = AsyncMock(side_effect=[5, 12, 1])

    backlog = await update_queue_backlog_metrics(
        redis_client=mock_redis,
        queue_names=["q1", "q2", "q3"],
    )

    assert backlog["q1"] == 5
    assert backlog["q2"] == 12
    assert backlog["q3"] == 1

    # Verify gauge label value
    val = TASK_QUEUE_BACKLOG.labels(queue_name="q1")._value.get()
    assert val == 5.0


@pytest.mark.asyncio
async def test_update_queue_backlog_handles_redis_error() -> None:
    """Verify update_queue_backlog handles exceptions gracefully without raising."""
    mock_redis = AsyncMock()
    mock_redis.llen = AsyncMock(side_effect=Exception("Connection refused"))

    backlog = await update_queue_backlog_metrics(
        redis_client=mock_redis,
        queue_names=["faulty_queue"],
    )
    assert backlog["faulty_queue"] == 0


def test_metrics_helpers_direct() -> None:
    """Verify calculation duration and worker metric collectors."""
    WEAR_CALCULATION_DURATION_SECONDS.observe(0.042)
    WEATHER_ENRICHMENT_DURATION_SECONDS.observe(0.125)
    TASK_EXECUTIONS_TOTAL.labels(task_name="test_task", status="success").inc()
    TASK_PROCESSING_DURATION_SECONDS.labels(task_name="test_task").observe(0.5)
    SYSTEM_HEALTH_STATUS.labels(component="test_component").set(1.0)

    payload, content_type = get_metrics_payload()
    assert len(payload) > 0
    assert "text/plain" in content_type
    assert b"velopulse_wear_calculation_duration_seconds" in payload
