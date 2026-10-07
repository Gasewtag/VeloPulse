"""Unit and integration tests for correlation tracing, middleware, and logging."""

import json
import logging
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from taskiq import TaskiqMessage, TaskiqResult

from velopulse.core.logging import (
    StructuredJSONFormatter,
    TextCorrelationFormatter,
    setup_logging,
)
from velopulse.observability.context import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from velopulse.observability.taskiq_middleware import TaskiqCorrelationMiddleware


@pytest.mark.asyncio
async def test_correlation_id_middleware_generated(async_client: AsyncClient) -> None:
    """Verify that a request without X-Correlation-ID receives a newly generated UUID."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    cid = response.headers.get("X-Correlation-ID")
    assert cid is not None
    assert len(cid) == 36  # Standard UUID-4 length


@pytest.mark.asyncio
async def test_correlation_id_middleware_preserved(async_client: AsyncClient) -> None:
    """Verify that incoming X-Correlation-ID is preserved and reflected in the response."""
    custom_cid = "trace-test-uuid-99999"
    response = await async_client.get("/health", headers={"X-Correlation-ID": custom_cid})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_cid


def test_context_var_helpers() -> None:
    """Verify set_correlation_id, get_correlation_id, and reset_correlation_id."""
    initial = get_correlation_id()
    assert initial == "" or isinstance(initial, str)

    token = set_correlation_id("custom-cid-123")
    assert get_correlation_id() == "custom-cid-123"

    reset_correlation_id(token)
    assert get_correlation_id() == initial


def test_structured_json_formatter() -> None:
    """Verify StructuredJSONFormatter produces valid JSON log records."""
    formatter = StructuredJSONFormatter()
    logger = logging.getLogger("test.structured.json")

    token = set_correlation_id("test-corr-id-abc")
    try:
        record = logger.makeRecord(
            name="test.logger",
            level=logging.INFO,
            fn="test_fn.py",
            lno=42,
            msg="User %s logged in",
            args=("alice",),
            exc_info=None,
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "User alice logged in"
        assert data["correlation_id"] == "test-corr-id-abc"
        assert "timestamp" in data
        assert data["line"] == 42
    finally:
        reset_correlation_id(token)


def test_structured_json_formatter_with_exception() -> None:
    """Verify StructuredJSONFormatter correctly formats exception stack traces."""
    formatter = StructuredJSONFormatter()
    logger = logging.getLogger("test.structured.exception")

    try:
        raise ValueError("Simulated computation failure")
    except ValueError:
        import sys

        record = logger.makeRecord(
            name="test.exception.logger",
            level=logging.ERROR,
            fn="test_err.py",
            lno=10,
            msg="An error occurred",
            args=(),
            exc_info=sys.exc_info(),
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)

        assert data["level"] == "ERROR"
        assert "Simulated computation failure" in data["exception"]


def test_text_correlation_formatter() -> None:
    """Verify TextCorrelationFormatter injects prefix into formatted text."""
    fmt = "%(levelname)s %(correlation_prefix)s %(message)s"
    formatter = TextCorrelationFormatter(fmt=fmt)
    logger = logging.getLogger("test.text.formatter")

    token = set_correlation_id("text-cid-555")
    try:
        record = logger.makeRecord(
            name="test.text",
            level=logging.WARNING,
            fn="test_text.py",
            lno=15,
            msg="Disk low",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        assert "[text-cid-555]" in formatted
        assert "Disk low" in formatted
    finally:
        reset_correlation_id(token)


def test_setup_logging_configurations() -> None:
    """Verify setup_logging works with text and json log formats."""
    setup_logging(debug=True, log_format="json")
    setup_logging(debug=False, log_format="text")


def test_taskiq_correlation_middleware_lifecycle() -> None:
    """Verify TaskiqCorrelationMiddleware pre_send, pre_execute, post_execute, and on_error."""
    middleware = TaskiqCorrelationMiddleware()

    # 1. Pre-send with active correlation ID
    token = set_correlation_id("taskiq-trace-001")
    try:
        msg = TaskiqMessage(
            task_id="task-123",
            task_name="test_worker_task",
            labels={},
            args=[],
            kwargs={},
        )
        updated_msg = middleware.pre_send(msg)
        assert updated_msg.labels.get("correlation_id") == "taskiq-trace-001"
    finally:
        reset_correlation_id(token)

    # 2. Pre-execute inside worker
    incoming_msg = TaskiqMessage(
        task_id="task-456",
        task_name="test_worker_task",
        labels={"correlation_id": "incoming-trace-456"},
        args=[],
        kwargs={},
    )
    middleware.pre_execute(incoming_msg)
    assert get_correlation_id() == "incoming-trace-456"

    # 3. Post-execute on success
    mock_result = MagicMock(spec=TaskiqResult)
    middleware.post_execute(incoming_msg, mock_result)
    # Correlation ID should be restored
    assert get_correlation_id() != "incoming-trace-456"

    # 4. Error path
    err_msg = TaskiqMessage(
        task_id="task-789",
        task_name="failed_worker_task",
        labels={"correlation_id": "err-trace-789"},
        args=[],
        kwargs={},
    )
    middleware.pre_execute(err_msg)
    assert get_correlation_id() == "err-trace-789"
    middleware.on_error(err_msg, mock_result, RuntimeError("Worker failure"))
    assert get_correlation_id() != "err-trace-789"
