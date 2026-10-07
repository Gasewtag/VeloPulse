"""Unit tests for Taskiq broker and DLQ middleware."""

from unittest.mock import AsyncMock, patch

import pytest
from taskiq import TaskiqMessage, TaskiqResult

from velopulse.tasks.broker import DLQMiddleware


@pytest.mark.asyncio
async def test_dlq_middleware_lifecycle() -> None:
    """Verify DLQMiddleware startup, on_error push to Redis, and shutdown."""
    mock_redis = AsyncMock()
    mock_redis.lpush = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch("velopulse.tasks.broker.Redis.from_url", return_value=mock_redis):
        middleware = DLQMiddleware("redis://mock:6379/0")
        await middleware.startup()
        assert middleware.redis_client is mock_redis

        msg = TaskiqMessage(
            task_id="failed-task-1",
            task_name="failed_task",
            labels={},
            args=[123],
            kwargs={},
        )
        res = TaskiqResult(
            is_err=True,
            log=None,
            return_value=None,
            execution_time=0.1,
        )

        await middleware.on_error(msg, res, RuntimeError("Boom"))
        mock_redis.lpush.assert_called_once()
        args = mock_redis.lpush.call_args[0]
        assert args[0] == "velopulse:dlq:failed_tasks"

        await middleware.shutdown()
        mock_redis.aclose.assert_called_once()
