"""Taskiq broker initialization and configuration."""

import logging
from redis.asyncio import Redis
import taskiq_fastapi
from taskiq import TaskiqMiddleware, TaskiqMessage, TaskiqResult
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from velopulse.core.config import get_settings

logger = logging.getLogger("velopulse.tasks.broker")
settings = get_settings()


class DLQMiddleware(TaskiqMiddleware):
    """Dead-Letter Queue middleware for capturing unrecoverable task failures."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client = None

    async def startup(self) -> None:
        """Initialize Redis connection for DLQ."""
        self.redis_client = Redis.from_url(self.redis_url, decode_responses=True)

    async def shutdown(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.aclose()

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult,
        exception: BaseException,
    ) -> None:
        """Push failed task payload to DLQ in Redis."""
        logger.error(
            "Task %s[%s] failed permanently. Moving to DLQ. Error: %s",
            message.task_name,
            message.task_id,
            exception,
        )
        if self.redis_client:
            dlq_key = "velopulse:dlq:failed_tasks"
            await self.redis_client.lpush(dlq_key, message.model_dump_json())


# Initialize result backend
result_backend = RedisAsyncResultBackend(
    redis_url=settings.REDIS_URL,
)

# Initialize the message broker using Redis with DLQ middleware
broker = ListQueueBroker(
    url=settings.REDIS_URL,
).with_result_backend(result_backend).with_middlewares(DLQMiddleware(settings.REDIS_URL))

# Initialize Taskiq for FastAPI to integrate dependency injection
taskiq_fastapi.init(broker, "velopulse.main:app")

