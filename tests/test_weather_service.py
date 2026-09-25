"""Tests for WeatherEnrichmentService and Wm physics calculations."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from velopulse.core.config import Settings
from velopulse.domain.weather import (
    OpenMeteoHourlyResponse,
    OpenMeteoResponse,
    SurfaceCondition,
)
from velopulse.services.weather.client import OpenMeteoClient
from velopulse.services.weather.service import WeatherEnrichmentService


@pytest.fixture
def test_settings() -> Settings:
    """Provide testing settings."""
    return Settings(STRAVA_MOCK_MODE=True)


@pytest.mark.asyncio
async def test_enrich_indoor_activity(test_settings: Settings) -> None:
    """Verify activities without GPS coordinates are classified as INDOOR_DRY with Wm=1.0."""
    service = WeatherEnrichmentService(settings=test_settings)
    result = await service.enrich_activity_weather(
        start_latitude=None,
        start_longitude=None,
        start_time=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        moving_time_s=3600,
    )

    assert result.is_indoor is True
    assert result.surface_condition == SurfaceCondition.INDOOR_DRY
    assert result.weather_multiplier == 1.0
    assert result.total_precipitation_mm == 0.0
    assert result.surface_wetness_index == 0.0


@pytest.mark.asyncio
async def test_enrich_dry_activity(test_settings: Settings) -> None:
    """Verify dry outdoor ride results in DRY surface and Wm=1.0."""
    mock_client = AsyncMock(spec=OpenMeteoClient)
    # Return dry readings
    mock_client.get_hourly_weather.return_value = OpenMeteoResponse(
        latitude=52.52,
        longitude=13.41,
        hourly=OpenMeteoHourlyResponse(
            time=["2026-07-10T10:00", "2026-07-10T11:00"],
            temperature_2m=[22.0, 23.5],
            precipitation=[0.0, 0.0],
            rain=[0.0, 0.0],
            snowfall=[0.0, 0.0],
            weather_code=[0, 1],
        ),
    )

    # Use a dummy cache that always misses
    mock_cache = AsyncMock()
    mock_cache.get_hourly_metric.return_value = None

    service = WeatherEnrichmentService(client=mock_client, cache=mock_cache, settings=test_settings)
    result = await service.enrich_activity_weather(
        start_latitude=52.52,
        start_longitude=13.41,
        start_time=datetime(2026, 7, 10, 10, 15, tzinfo=UTC),
        moving_time_s=3600,
        bike_type="Road",
    )

    assert result.surface_condition == SurfaceCondition.DRY
    assert result.weather_multiplier == 1.0
    assert result.total_precipitation_mm == 0.0
    assert result.average_temperature_c == 22.8


@pytest.mark.asyncio
async def test_enrich_damp_activity(test_settings: Settings) -> None:
    """Verify light precipitation/drizzle yields DAMP surface condition and 1.3 <= Wm <= 1.6."""
    mock_client = AsyncMock(spec=OpenMeteoClient)
    mock_client.get_hourly_weather.return_value = OpenMeteoResponse(
        latitude=52.52,
        longitude=13.41,
        hourly=OpenMeteoHourlyResponse(
            time=["2026-07-10T10:00"],
            temperature_2m=[16.0],
            precipitation=[0.2],
            rain=[0.2],
            snowfall=[0.0],
            weather_code=[51],
        ),
    )
    mock_cache = AsyncMock()
    mock_cache.get_hourly_metric.return_value = None

    service = WeatherEnrichmentService(client=mock_client, cache=mock_cache, settings=test_settings)
    result = await service.enrich_activity_weather(
        start_latitude=52.52,
        start_longitude=13.41,
        start_time=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        moving_time_s=1800,
        bike_type="Road",
    )

    assert result.surface_condition == SurfaceCondition.DAMP
    assert 1.3 <= result.weather_multiplier <= 1.6
    assert result.surface_wetness_index > 0.0


@pytest.mark.asyncio
async def test_enrich_wet_rain_activity(test_settings: Settings) -> None:
    """Verify active rain yields WET_RAIN surface condition and 1.8 <= Wm <= 2.4."""
    mock_client = AsyncMock(spec=OpenMeteoClient)
    mock_client.get_hourly_weather.return_value = OpenMeteoResponse(
        latitude=52.52,
        longitude=13.41,
        hourly=OpenMeteoHourlyResponse(
            time=["2026-07-10T10:00", "2026-07-10T11:00"],
            temperature_2m=[14.0, 14.5],
            precipitation=[1.5, 1.2],
            rain=[1.5, 1.2],
            snowfall=[0.0, 0.0],
            weather_code=[63, 63],
        ),
    )
    mock_cache = AsyncMock()
    mock_cache.get_hourly_metric.return_value = None

    service = WeatherEnrichmentService(client=mock_client, cache=mock_cache, settings=test_settings)
    result = await service.enrich_activity_weather(
        start_latitude=52.52,
        start_longitude=13.41,
        start_time=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        moving_time_s=5400,
        bike_type="Road",
    )

    assert result.surface_condition == SurfaceCondition.WET_RAIN
    assert 1.8 <= result.weather_multiplier <= 2.4
    assert result.surface_wetness_index == 1.0


@pytest.mark.asyncio
async def test_enrich_mud_grit_activity(test_settings: Settings) -> None:
    """Verify gravel/offroad ride with rain results in MUD_GRIT with 2.5 <= Wm <= 3.5."""
    mock_client = AsyncMock(spec=OpenMeteoClient)
    mock_client.get_hourly_weather.return_value = OpenMeteoResponse(
        latitude=52.52,
        longitude=13.41,
        hourly=OpenMeteoHourlyResponse(
            time=["2026-07-10T10:00", "2026-07-10T11:00"],
            temperature_2m=[11.0, 11.5],
            precipitation=[2.5, 3.0],
            rain=[2.5, 3.0],
            snowfall=[0.0, 0.0],
            weather_code=[65, 65],
        ),
    )
    mock_cache = AsyncMock()
    mock_cache.get_hourly_metric.return_value = None

    service = WeatherEnrichmentService(client=mock_client, cache=mock_cache, settings=test_settings)
    result = await service.enrich_activity_weather(
        start_latitude=52.52,
        start_longitude=13.41,
        start_time=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        moving_time_s=7200,
        bike_type="Gravel",
    )

    assert result.surface_condition == SurfaceCondition.MUD_GRIT
    assert 2.5 <= result.weather_multiplier <= 3.5


@pytest.mark.asyncio
async def test_enrich_subzero_winter_activity(test_settings: Settings) -> None:
    """Verify freezing temperatures incur the +0.2 cold temperature penalty."""
    mock_client = AsyncMock(spec=OpenMeteoClient)
    mock_client.get_hourly_weather.return_value = OpenMeteoResponse(
        latitude=52.52,
        longitude=13.41,
        hourly=OpenMeteoHourlyResponse(
            time=["2026-01-15T10:00"],
            temperature_2m=[-4.5],
            precipitation=[0.0],
            rain=[0.0],
            snowfall=[0.0],
            weather_code=[0],
        ),
    )
    mock_cache = AsyncMock()
    mock_cache.get_hourly_metric.return_value = None

    service = WeatherEnrichmentService(client=mock_client, cache=mock_cache, settings=test_settings)
    result = await service.enrich_activity_weather(
        start_latitude=52.52,
        start_longitude=13.41,
        start_time=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        moving_time_s=3600,
        bike_type="Road",
    )

    assert result.average_temperature_c == -4.5
    assert result.weather_multiplier >= 1.2
