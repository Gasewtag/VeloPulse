"""Tests for WeatherCache Redis integration."""

from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis

from velopulse.core.config import get_settings
from velopulse.domain.weather import HourlyWeatherMetric
from velopulse.services.weather.cache import WeatherCache


@pytest.mark.asyncio
async def test_weather_cache_roundtrip() -> None:
    """Verify storing and retrieving an HourlyWeatherMetric from Redis."""
    settings = get_settings()
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    cache = WeatherCache(redis_client=redis_client, settings=settings)

    metric = HourlyWeatherMetric(
        time=datetime(2026, 8, 1, 14, 0, tzinfo=UTC),
        temperature_2m=24.5,
        precipitation=0.0,
        rain=0.0,
        snowfall=0.0,
        weather_code=1,
    )

    lat, lng = 52.5234, 13.4123
    await cache.set_hourly_metric(lat, lng, metric)

    retrieved = await cache.get_hourly_metric(lat, lng, metric.time)
    assert retrieved is not None
    assert retrieved.temperature_2m == 24.5
    assert retrieved.weather_code == 1

    # Clean up
    key = WeatherCache.format_key(lat, lng, metric.time)
    await redis_client.delete(key)
    await redis_client.aclose()


@pytest.mark.asyncio
async def test_weather_cache_batch() -> None:
    """Verify batch storing and retrieving multiple hourly observations."""
    settings = get_settings()
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    cache = WeatherCache(redis_client=redis_client, settings=settings)

    metrics = [
        HourlyWeatherMetric(
            time=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
            temperature_2m=21.0,
            precipitation=0.0,
            rain=0.0,
            snowfall=0.0,
            weather_code=0,
        ),
        HourlyWeatherMetric(
            time=datetime(2026, 8, 1, 11, 0, tzinfo=UTC),
            temperature_2m=22.5,
            precipitation=1.2,
            rain=1.2,
            snowfall=0.0,
            weather_code=61,
        ),
    ]

    lat, lng = 45.123, 7.456
    await cache.set_hourly_metrics(lat, lng, metrics)

    m1 = await cache.get_hourly_metric(lat, lng, metrics[0].time)
    m2 = await cache.get_hourly_metric(lat, lng, metrics[1].time)

    assert m1 is not None and m1.temperature_2m == 21.0
    assert m2 is not None and m2.precipitation == 1.2

    # Clean up
    k1 = WeatherCache.format_key(lat, lng, metrics[0].time)
    k2 = WeatherCache.format_key(lat, lng, metrics[1].time)
    await redis_client.delete(k1, k2)
    await redis_client.aclose()


def test_weather_cache_key_precision() -> None:
    """Verify coordinate rounding to ~1.1km grid precision."""
    dt = datetime(2026, 5, 20, 15, 30, tzinfo=UTC)
    k1 = WeatherCache.format_key(52.52111, 13.40111, dt)
    k2 = WeatherCache.format_key(52.52444, 13.40444, dt)

    assert k1 == k2
    assert k1 == "weather:52.52:13.40:2026-05-20T15"
