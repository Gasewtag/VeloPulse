"""Redis caching layer for geo-temporal weather observations."""

import json
import logging
from datetime import datetime

from redis.asyncio import Redis

from velopulse.core.config import Settings, get_settings
from velopulse.domain.weather import HourlyWeatherMetric

logger = logging.getLogger("velopulse.services.weather.cache")


class WeatherCache:
    """Cache-aside provider for hourly meteorological readings."""

    def __init__(
        self,
        redis_client: Redis | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._redis = redis_client
        self._owns_client = redis_client is None

    async def _get_redis(self) -> Redis:
        """Get or initialize Redis connection."""
        if self._redis is None:
            self._redis = Redis.from_url(self.settings.REDIS_URL, decode_responses=True)
        return self._redis

    @staticmethod
    def format_key(latitude: float, longitude: float, dt: datetime) -> str:
        """Format a Redis key rounded to ~1.1km grid precision and 1-hour time buckets."""
        lat_grid = f"{latitude:.2f}"
        lng_grid = f"{longitude:.2f}"
        hour_bucket = dt.strftime("%Y-%m-%dT%H")
        return f"weather:{lat_grid}:{lng_grid}:{hour_bucket}"

    async def get_hourly_metric(
        self, latitude: float, longitude: float, dt: datetime
    ) -> HourlyWeatherMetric | None:
        """Retrieve a cached hourly metric from Redis, if present."""
        try:
            r = await self._get_redis()
            key = self.format_key(latitude, longitude, dt)
            cached_val = await r.get(key)
            if cached_val:
                data = json.loads(cached_val)
                return HourlyWeatherMetric.model_validate(data)
        except Exception as exc:
            logger.warning(f"Error reading from weather cache: {exc}")
        return None

    async def set_hourly_metric(
        self, latitude: float, longitude: float, metric: HourlyWeatherMetric
    ) -> None:
        """Store an hourly observation into Redis with expiration TTL."""
        try:
            r = await self._get_redis()
            key = self.format_key(latitude, longitude, metric.time)
            json_data = json.dumps(metric.model_dump(mode="json"))
            await r.set(key, json_data, ex=self.settings.WEATHER_CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.warning(f"Error writing to weather cache: {exc}")

    async def set_hourly_metrics(
        self, latitude: float, longitude: float, metrics: list[HourlyWeatherMetric]
    ) -> None:
        """Batch store a list of hourly observations into Redis."""
        try:
            r = await self._get_redis()
            async with r.pipeline(transaction=False) as pipe:
                for metric in metrics:
                    key = self.format_key(latitude, longitude, metric.time)
                    json_data = json.dumps(metric.model_dump(mode="json"))
                    pipe.set(key, json_data, ex=self.settings.WEATHER_CACHE_TTL_SECONDS)
                await pipe.execute()
        except Exception as exc:
            logger.warning(f"Error writing batch to weather cache: {exc}")

    async def close(self) -> None:
        """Close connection if owned by this instance."""
        if self._owns_client and self._redis is not None:
            await self._redis.aclose()
            self._redis = None
