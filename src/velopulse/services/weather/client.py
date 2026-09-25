"""HTTP client for Open-Meteo Historical Archive and Forecast APIs."""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from velopulse.core.config import Settings, get_settings
from velopulse.domain.weather import (
    OpenMeteoHourlyResponse,
    OpenMeteoResponse,
)

logger = logging.getLogger("velopulse.services.weather.client")


class OpenMeteoAPIError(Exception):
    """Exception raised when an Open-Meteo API request fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class OpenMeteoClient:
    """Asynchronous client interacting with Open-Meteo REST endpoints."""

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
        mock_mode: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._http_client = http_client
        self.mock_mode = (
            mock_mode if mock_mode is not None else self.settings.STRAVA_MOCK_MODE
        )

    async def get_hourly_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> OpenMeteoResponse:
        """Fetch hourly meteorological variables for the given geographic location and date span.

        Args:
            latitude: Geographic latitude in decimal degrees.
            longitude: Geographic longitude in decimal degrees.
            start_date: Beginning date of observation period (YYYY-MM-DD).
            end_date: Ending date of observation period (YYYY-MM-DD).

        Returns:
            OpenMeteoResponse containing hourly observation arrays.

        Raises:
            OpenMeteoAPIError: If the remote endpoint returns a 4xx/5xx or network fails.
        """
        if self.mock_mode:
            logger.info(
                f"[MOCK] Returning synthetic Open-Meteo data for ({latitude}, {longitude}) from {start_date} to {end_date}"
            )
            return self._generate_mock_weather(latitude, longitude, start_date, end_date)

        # Open-Meteo Forecast endpoint serves recent history (past 90 days) with low latency.
        # Older historical dates require the Historical Archive endpoint.
        today = datetime.now(UTC).date()
        days_ago = (today - start_date).days
        url = (
            self.settings.OPEN_METEO_FORECAST_URL
            if days_ago <= 90
            else self.settings.OPEN_METEO_BASE_URL
        )

        params: dict[str, Any] = {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": "temperature_2m,precipitation,rain,snowfall,weather_code",
            "timezone": "UTC",
        }

        should_close = False
        client = self._http_client
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True

        try:
            logger.debug(f"Requesting weather from {url} with params {params}")
            response = await client.get(url, params=params)

            if response.status_code == 429:
                logger.warning(f"Open-Meteo rate limit hit: {response.text}")
                raise OpenMeteoAPIError(
                    "Open-Meteo rate limit exceeded",
                    status_code=429,
                    response_body=response.text,
                )

            if response.is_error:
                logger.error(
                    f"Open-Meteo HTTP {response.status_code} error: {response.text}"
                )
                raise OpenMeteoAPIError(
                    f"Open-Meteo returned status {response.status_code}: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )

            data = response.json()
            return OpenMeteoResponse.model_validate(data)

        except httpx.RequestError as exc:
            logger.error(f"Open-Meteo network request failed: {exc}")
            raise OpenMeteoAPIError(f"Network error querying Open-Meteo: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    def _generate_mock_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> OpenMeteoResponse:
        """Generate realistic synthetic hourly meteorological observations for offline execution."""
        times: list[str] = []
        temps: list[float] = []
        precips: list[float] = []
        rains: list[float] = []
        snows: list[float] = []
        codes: list[int] = []

        curr_date = start_date
        while curr_date <= end_date:
            for hour in range(24):
                dt_str = f"{curr_date.isoformat()}T{hour:02d}:00"
                times.append(dt_str)

                # Synthetic scenario variation based on test coordinates
                if abs(latitude - 99.0) < 0.1:
                    # Test coordinate for torrential rain & mud
                    temp = 12.0
                    precip = 6.5
                    rain = 6.5
                    snow = 0.0
                    code = 65  # Heavy rain
                elif abs(latitude - 88.0) < 0.1:
                    # Test coordinate for damp road spray
                    temp = 14.0
                    precip = 0.3
                    rain = 0.3
                    snow = 0.0
                    code = 51  # Light drizzle
                elif abs(latitude - 77.0) < 0.1:
                    # Test coordinate for sub-zero freezing winter ride
                    temp = -3.5
                    precip = 0.0
                    rain = 0.0
                    snow = 0.2
                    code = 71  # Slight snowfall
                else:
                    # Default dry asphalt ride (optimal conditions)
                    # Diurnal curve: 12°C at night, 22°C mid-afternoon
                    temp = round(14.0 + 8.0 * ((hour - 4) % 24) / 24.0, 1)
                    precip = 0.0
                    rain = 0.0
                    snow = 0.0
                    code = 0  # Clear sky

                temps.append(temp)
                precips.append(precip)
                rains.append(rain)
                snows.append(snow)
                codes.append(code)

            curr_date += timedelta(days=1)

        return OpenMeteoResponse(
            latitude=latitude,
            longitude=longitude,
            generationtime_ms=0.15,
            utc_offset_seconds=0,
            timezone="UTC",
            timezone_abbreviation="UTC",
            elevation=50.0,
            hourly=OpenMeteoHourlyResponse(
                time=times,
                temperature_2m=temps,
                precipitation=precips,
                rain=rains,
                snowfall=snows,
                weather_code=codes,
            ),
        )
