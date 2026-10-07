"""Taskiq middleware for distributed correlation ID propagation and task telemetry."""

import logging
import time
from typing import Any

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from velopulse.observability.context import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from velopulse.observability.metrics import (
    TASK_EXECUTIONS_TOTAL,
    TASK_PROCESSING_DURATION_SECONDS,
)

logger = logging.getLogger("velopulse.observability.taskiq")


class TaskiqCorrelationMiddleware(TaskiqMiddleware):
    """Propagates correlation IDs across asynchronous Taskiq task dispatches and logs."""

    def __init__(self) -> None:
        self._tokens: dict[str, Any] = {}
        self._start_times: dict[str, float] = {}

    def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        """Inject current correlation ID into outgoing task message labels."""
        cid = get_correlation_id()
        if cid:
            message.labels["correlation_id"] = cid
        return message

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Extract correlation ID from incoming task labels and initialize task execution."""
        cid = message.labels.get("correlation_id")
        token = set_correlation_id(cid)
        self._tokens[message.task_id] = token
        self._start_times[message.task_id] = time.perf_counter()

        logger.info(
            "Background task starting: task=%s, id=%s, correlation_id=%s",
            message.task_name,
            message.task_id,
            get_correlation_id(),
        )
        return message

    def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:
        """Record task execution latency and update Prometheus metrics on completion."""
        start_time = self._start_times.pop(message.task_id, None)
        duration = time.perf_counter() - start_time if start_time is not None else 0.0

        TASK_EXECUTIONS_TOTAL.labels(task_name=message.task_name, status="success").inc()
        TASK_PROCESSING_DURATION_SECONDS.labels(task_name=message.task_name).observe(duration)

        logger.info(
            "Background task succeeded: task=%s, id=%s, duration=%.3fs, correlation_id=%s",
            message.task_name,
            message.task_id,
            duration,
            get_correlation_id(),
        )

        token = self._tokens.pop(message.task_id, None)
        if token is not None:
            reset_correlation_id(token)

    def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        """Record task failure status and cleanup execution context."""
        start_time = self._start_times.pop(message.task_id, None)
        duration = time.perf_counter() - start_time if start_time is not None else 0.0

        TASK_EXECUTIONS_TOTAL.labels(task_name=message.task_name, status="failure").inc()
        TASK_PROCESSING_DURATION_SECONDS.labels(task_name=message.task_name).observe(duration)

        logger.error(
            "Background task failed: task=%s, id=%s, duration=%.3fs, error=%s, correlation_id=%s",
            message.task_name,
            message.task_id,
            duration,
            exception,
            get_correlation_id(),
        )

        token = self._tokens.pop(message.task_id, None)
        if token is not None:
            reset_correlation_id(token)
