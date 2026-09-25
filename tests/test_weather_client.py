"""Tests for OpenMeteoClient."""

from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from velopulse.core.config import Settings
from velopulse.domain.weather import OpenMeteoResponse
from velopulse.services.weather.client import OpenMeteoAPIError, OpenMeteoClient


@pytest.fixture
def weather_settings() -> Settings:
    """Provide settings with configured Open-Meteo URLs."""
    return Settings(
        STRAVA_MOCK_MODE=True,
        OPEN_METEO_BASE_URL="https://archive-api.open-meteo.com/v1/archive",
        OPEN_METEO_FORECAST_URL="https://api.open-meteo.com/v1/forecast",
    )


@pytest.mark.asyncio
async def test_open_meteo_client_mock_mode_default(weather_settings: Settings) -> None:
    """Verify mock mode generates standard dry day observations offline."""
    client = OpenMeteoClient(settings=weather_settings, mock_mode=True)
    resp = await client.get_hourly_weather(
        latitude=52.52,
        longitude=13.41,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
    )

    assert isinstance(resp, OpenMeteoResponse)
    assert resp.latitude == 52.52
    assert resp.longitude == 13.41
    assert len(resp.hourly.time) == 24

    metrics = resp.to_hourly_metrics()
    assert len(metrics) == 24
    assert all(m.precipitation == 0.0 for m in metrics)
    assert all(m.snowfall == 0.0 for m in metrics)
    assert 10.0 <= metrics[12].temperature_2m <= 25.0


@pytest.mark.asyncio
async def test_open_meteo_client_mock_mode_rain_and_snow(
    weather_settings: Settings,
) -> None:
    """Verify mock mode generates scenario-specific conditions based on coordinates."""
    client = OpenMeteoClient(settings=weather_settings, mock_mode=True)

    # Coordinates 99.0 trigger rain
    rain_resp = await client.get_hourly_weather(
        latitude=99.0,
        longitude=10.0,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
    )
    rain_metrics = rain_resp.to_hourly_metrics()
    assert rain_metrics[0].precipitation > 0.0
    assert rain_metrics[0].weather_code == 65

    # Coordinates 77.0 trigger freezing snow
    snow_resp = await client.get_hourly_weather(
        latitude=77.0,
        longitude=10.0,
        start_date=date(2026, 1, 15),
        end_date=date(2026, 1, 15),
    )
    snow_metrics = snow_resp.to_hourly_metrics()
    assert snow_metrics[0].temperature_2m < 0.0
    assert snow_metrics[0].snowfall > 0.0


@pytest.mark.asyncio
@respx.mock
async def test_open_meteo_client_http_success(weather_settings: Settings) -> None:
    """Verify Open-Meteo HTTP request formatting and response deserialization."""
    mock_payload = {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "generationtime_ms": 0.12,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "elevation": 35.0,
        "hourly": {
            "time": ["2026-06-01T10:00", "2026-06-01T11:00"],
            "temperature_2m": [21.5, 22.0],
            "precipitation": [0.0, 0.4],
            "rain": [0.0, 0.4],
            "snowfall": [0.0, 0.0],
            "weather_code": [1, 51],
        },
    }

    route = respx.get("https://api.open-meteo.com/v1/forecast").respond(
        status_code=200, json=mock_payload
    )

    async with httpx.AsyncClient() as http_client:
        client = OpenMeteoClient(
            settings=weather_settings, http_client=http_client, mock_mode=False
        )
        today = datetime.now(UTC).date()
        result = await client.get_hourly_weather(
            latitude=48.8566,
            longitude=2.3522,
            start_date=today,
            end_date=today,
        )

    assert route.called
    assert result.latitude == 48.8566
    metrics = result.to_hourly_metrics()
    assert len(metrics) == 2
    assert metrics[0].temperature_2m == 21.5
    assert metrics[1].precipitation == 0.4
    assert metrics[1].weather_code == 51


@pytest.mark.asyncio
@respx.mock
async def test_open_meteo_client_rate_limit(weather_settings: Settings) -> None:
    """Verify HTTP 429 raises OpenMeteoAPIError with code 429."""
    respx.get("https://api.open-meteo.com/v1/forecast").respond(
        status_code=429, text="Hourly API request limit exceeded"
    )

    async with httpx.AsyncClient() as http_client:
        client = OpenMeteoClient(
            settings=weather_settings, http_client=http_client, mock_mode=False
        )
        today = datetime.now(UTC).date()
        with pytest.raises(OpenMeteoAPIError) as exc_info:
            await client.get_hourly_weather(
                latitude=52.52,
                longitude=13.41,
                start_date=today,
                end_date=today,
            )

    assert exc_info.value.status_code == 429
    assert "rate limit" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_open_meteo_client_server_error(weather_settings: Settings) -> None:
    """Verify HTTP 500 raises OpenMeteoAPIError with code 500."""
    respx.get("https://api.open-meteo.com/v1/forecast").respond(
        status_code=500, text="Internal Server Error"
    )

    async with httpx.AsyncClient() as http_client:
        client = OpenMeteoClient(
            settings=weather_settings, http_client=http_client, mock_mode=False
        )
        today = datetime.now(UTC).date()
        with pytest.raises(OpenMeteoAPIError) as exc_info:
            await client.get_hourly_weather(
                latitude=52.52,
                longitude=13.41,
                start_date=today,
                end_date=today,
            )

    assert exc_info.value.status_code == 500
