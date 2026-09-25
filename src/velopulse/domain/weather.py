"""Weather domain schemas, enums, and data transfer objects."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SurfaceCondition(StrEnum):
    """Classification of road surface conditions based on meteorological data."""

    DRY = "DRY"
    DAMP = "DAMP"
    WET_RAIN = "WET_RAIN"
    MUD_GRIT = "MUD_GRIT"
    INDOOR_DRY = "INDOOR_DRY"


class HourlyWeatherMetric(BaseModel):
    """Meteorological reading for a specific one-hour time bucket."""

    model_config = ConfigDict(extra="ignore")

    time: datetime
    temperature_2m: float  # °C
    precipitation: float  # mm
    rain: float = 0.0  # mm
    snowfall: float = 0.0  # cm
    weather_code: int = 0  # WMO weather interpretation code


class OpenMeteoHourlyResponse(BaseModel):
    """Raw hourly arrays returned by the Open-Meteo REST API."""

    model_config = ConfigDict(extra="ignore")

    time: list[str] = Field(default_factory=list)
    temperature_2m: list[float] = Field(default_factory=list)
    precipitation: list[float] = Field(default_factory=list)
    rain: list[float] = Field(default_factory=list)
    snowfall: list[float] = Field(default_factory=list)
    weather_code: list[int] = Field(default_factory=list)


class OpenMeteoResponse(BaseModel):
    """Full payload schema returned by Open-Meteo archive or forecast endpoints."""

    model_config = ConfigDict(extra="ignore")

    latitude: float
    longitude: float
    generationtime_ms: float = 0.0
    utc_offset_seconds: int = 0
    timezone: str = "GMT"
    timezone_abbreviation: str = "GMT"
    elevation: float = 0.0
    hourly: OpenMeteoHourlyResponse = Field(default_factory=OpenMeteoHourlyResponse)

    def to_hourly_metrics(self) -> list[HourlyWeatherMetric]:
        """Convert parallel hourly arrays into a list of typed HourlyWeatherMetric objects."""
        metrics: list[HourlyWeatherMetric] = []
        hourly = self.hourly
        n = len(hourly.time)
        for i in range(n):
            dt = datetime.fromisoformat(hourly.time[i])
            temp = hourly.temperature_2m[i] if i < len(hourly.temperature_2m) else 15.0
            precip = hourly.precipitation[i] if i < len(hourly.precipitation) else 0.0
            rain = hourly.rain[i] if i < len(hourly.rain) else 0.0
            snow = hourly.snowfall[i] if i < len(hourly.snowfall) else 0.0
            code = hourly.weather_code[i] if i < len(hourly.weather_code) else 0
            metrics.append(
                HourlyWeatherMetric(
                    time=dt,
                    temperature_2m=temp,
                    precipitation=precip,
                    rain=rain,
                    snowfall=snow,
                    weather_code=code,
                )
            )
        return metrics


class WeatherEnrichmentResult(BaseModel):
    """Enriched weather telemetry calculated for a specific ride activity."""

    model_config = ConfigDict(extra="ignore")

    surface_condition: SurfaceCondition
    weather_multiplier: float  # Wm (calibrated 1.0 to 3.5)
    average_temperature_c: float
    total_precipitation_mm: float
    surface_wetness_index: float  # Sw in [0.0, 1.0]
    weather_code: int | None = None
    is_indoor: bool = False
    raw_meteo_summary: dict[str, Any] = Field(default_factory=dict)
