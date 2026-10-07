"""Prometheus metrics registry and telemetry collectors for VeloPulse."""

import logging
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from redis.asyncio import Redis

logger = logging.getLogger("velopulse.observability.metrics")

# ------------------------------------------------------------------------------
# HTTP Request Metrics
# ------------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "velopulse_http_requests_total",
    "Total count of HTTP requests handled by the FastAPI application.",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "velopulse_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ------------------------------------------------------------------------------
# Background Worker Metrics
# ------------------------------------------------------------------------------
TASK_EXECUTIONS_TOTAL = Counter(
    "velopulse_task_executions_total",
    "Total count of background tasks processed by Taskiq workers.",
    ["task_name", "status"],
)

TASK_PROCESSING_DURATION_SECONDS = Histogram(
    "velopulse_task_processing_duration_seconds",
    "Background task execution processing duration in seconds.",
    ["task_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

TASK_QUEUE_BACKLOG = Gauge(
    "velopulse_task_queue_backlog",
    "Number of pending tasks queued in Redis waiting for worker processing.",
    ["queue_name"],
)

# ------------------------------------------------------------------------------
# Business & Calculation Engine Metrics
# ------------------------------------------------------------------------------
WEAR_CALCULATION_DURATION_SECONDS = Histogram(
    "velopulse_wear_calculation_duration_seconds",
    "Duration of bicycle component wear calculation engine execution in seconds.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

WEATHER_ENRICHMENT_DURATION_SECONDS = Histogram(
    "velopulse_weather_enrichment_duration_seconds",
    "Duration of activity weather enrichment and caching in seconds.",
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# ------------------------------------------------------------------------------
# Health & Status Gauges
# ------------------------------------------------------------------------------
SYSTEM_HEALTH_STATUS = Gauge(
    "velopulse_system_health_status",
    "Health status probe of system components (1 = healthy/connected, 0 = degraded/unavailable).",
    ["component"],
)


async def update_queue_backlog_metrics(
    redis_client: Redis,
    queue_names: list[str] | None = None,
) -> dict[str, int]:
    """Query Redis list lengths for background task queues and update gauge metrics."""
    target_queues = queue_names or [
        "taskiq:queue:default",
        "velopulse:tasks",
        "velopulse:dlq:failed_tasks",
    ]
    backlog_counts: dict[str, int] = {}

    for q_name in target_queues:
        try:
            length: Any = await redis_client.llen(q_name)
            backlog_counts[q_name] = int(length)
            TASK_QUEUE_BACKLOG.labels(queue_name=q_name).set(float(length))
        except Exception as exc:
            logger.debug("Failed to read length for queue '%s': %s", q_name, exc)
            backlog_counts[q_name] = 0

    return backlog_counts


def get_metrics_payload() -> tuple[bytes, str]:
    """Generate Prometheus exposition format payload and corresponding media type."""
    return generate_latest(), CONTENT_TYPE_LATEST
