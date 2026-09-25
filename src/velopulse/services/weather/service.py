"""Domain service for geo-temporal weather telemetry extraction and physics multiplier calculation."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from velopulse.core.config import Settings, get_settings
from velopulse.domain.weather import (
    HourlyWeatherMetric,
    SurfaceCondition,
    WeatherEnrichmentResult,
)
from velopulse.services.weather.cache import WeatherCache
from velopulse.services.weather.client import OpenMeteoClient

logger = logging.getLogger("velopulse.services.weather.service")


class WeatherEnrichmentService:
    """Service that enriches cycling activities with meteorological conditions and wear factors."""

    def __init__(
        self,
        client: OpenMeteoClient | None = None,
        cache: WeatherCache | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenMeteoClient(settings=self.settings)
        self.cache = cache or WeatherCache(settings=self.settings)

    async def enrich_activity_weather(
        self,
        start_latitude: float | Decimal | None,
        start_longitude: float | Decimal | None,
        start_time: datetime,
        moving_time_s: int,
        bike_type: str | None = None,
    ) -> WeatherEnrichmentResult:
        """Calculate environmental weather telemetry and the Wm physics multiplier for an activity.

        Args:
            start_latitude: Starting latitude in decimal degrees, or None if indoor.
            start_longitude: Starting longitude in decimal degrees, or None if indoor.
            start_time: Start timestamp of the ride.
            moving_time_s: Moving time duration in seconds.
            bike_type: Optional bike type classification (e.g. 'Gravel', 'MTB', 'Road').

        Returns:
            WeatherEnrichmentResult containing surface condition and Wm wear factor.
        """
        # 1. Indoor / Manual activity handling
        if start_latitude is None or start_longitude is None:
            logger.info("Activity has no GPS coordinates; classifying as INDOOR_DRY.")
            return WeatherEnrichmentResult(
                surface_condition=SurfaceCondition.INDOOR_DRY,
                weather_multiplier=1.0,
                average_temperature_c=20.0,
                total_precipitation_mm=0.0,
                surface_wetness_index=0.0,
                weather_code=0,
                is_indoor=True,
                raw_meteo_summary={"reason": "No GPS coordinates (indoor or manual entry)"},
            )

        lat = float(start_latitude)
        lng = float(start_longitude)

        # Ensure start_time has timezone
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UTC)

        # 2. Determine time window
        duration_s = max(moving_time_s, 60)
        end_time = start_time + timedelta(seconds=duration_s)

        # Generate hourly timestamps covering the ride
        curr_hour = start_time.replace(minute=0, second=0, microsecond=0)
        end_hour = end_time.replace(minute=0, second=0, microsecond=0)

        required_hours: list[datetime] = []
        while curr_hour <= end_hour:
            required_hours.append(curr_hour)
            curr_hour += timedelta(hours=1)

        # 3. Retrieve metrics (with Redis cache-aside lookup)
        metrics: list[HourlyWeatherMetric] = []
        missing_hours: list[datetime] = []

        for h in required_hours:
            cached = await self.cache.get_hourly_metric(lat, lng, h)
            if cached is not None:
                metrics.append(cached)
            else:
                missing_hours.append(h)

        if missing_hours:
            min_date = min(h.date() for h in missing_hours)
            max_date = max(h.date() for h in missing_hours)
            try:
                open_meteo_resp = await self.client.get_hourly_weather(
                    lat, lng, min_date, max_date
                )
                fetched_metrics = open_meteo_resp.to_hourly_metrics()
                # Store in cache
                await self.cache.set_hourly_metrics(lat, lng, fetched_metrics)

                # Match missing hours
                fetched_map = {m.time.replace(minute=0, second=0, microsecond=0, tzinfo=UTC): m for m in fetched_metrics}
                for h in missing_hours:
                    h_utc = h.astimezone(UTC)
                    if h_utc in fetched_map:
                        metrics.append(fetched_map[h_utc])
            except Exception as exc:
                logger.error(f"Failed to fetch weather from Open-Meteo: {exc}")
                # If network fails and no cached data, fallback to default dry mild day
                if not metrics:
                    return self._generate_fallback_result(is_error=True)

        if not metrics:
            return self._generate_fallback_result()

        # 4. Aggregate meteorological metrics across ride hours
        temps = [m.temperature_2m for m in metrics]
        precips = [m.precipitation for m in metrics]
        rains = [m.rain for m in metrics]
        codes = [m.weather_code for m in metrics]

        avg_temp = round(sum(temps) / len(temps), 1)
        total_precip = round(sum(precips), 2)
        total_rain = round(sum(rains), 2)
        max_hourly_precip = max(precips)
        dominant_code = max(codes, key=codes.count)

        # 5. Compute Surface Wetness Index (Sw in [0.0, 1.0])
        if total_precip == 0.0:
            surface_wetness = 0.0
        elif total_precip < 0.5:
            surface_wetness = min(1.0, round(0.3 + 1.2 * total_precip, 2))
        else:
            surface_wetness = 1.0

        # 6. Surface Condition Classification
        is_offroad = bike_type is not None and bike_type.upper() in ["GRAVEL", "MTB"]
        if total_precip >= 5.0 or (total_precip >= 2.0 and is_offroad):
            surface_condition = SurfaceCondition.MUD_GRIT
        elif total_precip >= 0.5 or max_hourly_precip >= 1.0:
            surface_condition = SurfaceCondition.WET_RAIN
        elif total_precip > 0.0 or surface_wetness >= 0.3:
            surface_condition = SurfaceCondition.DAMP
        else:
            surface_condition = SurfaceCondition.DRY

        # 7. Compute Environmental Multiplier Wm per ARCHITECTURE.md
        # Wm = 1.0 + (beta_rain * P) + (beta_wet * Sw) + Phi_temp(T)
        beta_rain = 0.4
        beta_wet = 0.4
        temp_penalty = 0.2 if avg_temp < 0.0 else 0.0

        raw_multiplier = 1.0 + (beta_rain * max_hourly_precip) + (beta_wet * surface_wetness) + temp_penalty

        # Category minimum floor calibration:
        # Dry: 1.0x, Damp: 1.3x - 1.5x, Wet Rain: 1.8x - 2.2x, Mud / Slurry: 2.5x - 3.5x
        if surface_condition == SurfaceCondition.MUD_GRIT:
            wm = max(2.5, min(3.5, raw_multiplier + 1.0))
        elif surface_condition == SurfaceCondition.WET_RAIN:
            wm = max(1.8, min(2.4, raw_multiplier + 0.3))
        elif surface_condition == SurfaceCondition.DAMP:
            wm = max(1.3, min(1.6, raw_multiplier))
        else:
            wm = max(1.0, 1.0 + temp_penalty)

        # Final clamp: [1.0, 3.5]
        wm = round(max(1.0, min(3.5, wm)), 2)

        return WeatherEnrichmentResult(
            surface_condition=surface_condition,
            weather_multiplier=wm,
            average_temperature_c=avg_temp,
            total_precipitation_mm=total_precip,
            surface_wetness_index=surface_wetness,
            weather_code=dominant_code,
            is_indoor=False,
            raw_meteo_summary={
                "total_rain_mm": total_rain,
                "max_hourly_precip_mm": max_hourly_precip,
                "dominant_wmo_code": dominant_code,
                "hours_sampled": len(metrics),
            },
        )

    def _generate_fallback_result(self, is_error: bool = False) -> WeatherEnrichmentResult:
        """Return fallback weather telemetry when external service is inaccessible."""
        return WeatherEnrichmentResult(
            surface_condition=SurfaceCondition.DRY,
            weather_multiplier=1.0,
            average_temperature_c=18.0,
            total_precipitation_mm=0.0,
            surface_wetness_index=0.0,
            weather_code=0,
            is_indoor=False,
            raw_meteo_summary={"fallback": True, "error": is_error},
        )
