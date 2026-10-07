"""Observability, telemetry, and structured tracing package for VeloPulse."""

from velopulse.observability.context import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from velopulse.observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    SYSTEM_HEALTH_STATUS,
    TASK_EXECUTIONS_TOTAL,
    TASK_PROCESSING_DURATION_SECONDS,
    TASK_QUEUE_BACKLOG,
    WEAR_CALCULATION_DURATION_SECONDS,
    WEATHER_ENRICHMENT_DURATION_SECONDS,
    get_metrics_payload,
    update_queue_backlog_metrics,
)
from velopulse.observability.middleware import (
    CorrelationIdMiddleware,
    PrometheusMetricsMiddleware,
)
from velopulse.observability.taskiq_middleware import TaskiqCorrelationMiddleware

__all__ = [
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    "SYSTEM_HEALTH_STATUS",
    "TASK_EXECUTIONS_TOTAL",
    "TASK_PROCESSING_DURATION_SECONDS",
    "TASK_QUEUE_BACKLOG",
    "WEAR_CALCULATION_DURATION_SECONDS",
    "WEATHER_ENRICHMENT_DURATION_SECONDS",
    "CorrelationIdMiddleware",
    "PrometheusMetricsMiddleware",
    "TaskiqCorrelationMiddleware",
    "get_correlation_id",
    "get_metrics_payload",
    "reset_correlation_id",
    "set_correlation_id",
    "update_queue_backlog_metrics",
]
