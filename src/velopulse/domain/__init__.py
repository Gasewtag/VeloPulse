"""Domain models, entities, and enums."""

from velopulse.domain.strava import (
    StravaAthleteSummary,
    StravaGearSummary,
    StravaRefreshTokenResponse,
    StravaSubscription,
    StravaTokenResponse,
    StravaWebhookChallenge,
    StravaWebhookChallengeResponse,
    StravaWebhookEvent,
)
from velopulse.domain.weather import (
    HourlyWeatherMetric,
    OpenMeteoHourlyResponse,
    OpenMeteoResponse,
    SurfaceCondition,
    WeatherEnrichmentResult,
)

__all__ = [
    "HourlyWeatherMetric",
    "OpenMeteoHourlyResponse",
    "OpenMeteoResponse",
    "StravaAthleteSummary",
    "StravaGearSummary",
    "StravaRefreshTokenResponse",
    "StravaSubscription",
    "StravaTokenResponse",
    "StravaWebhookChallenge",
    "StravaWebhookChallengeResponse",
    "StravaWebhookEvent",
    "SurfaceCondition",
    "WeatherEnrichmentResult",
]

