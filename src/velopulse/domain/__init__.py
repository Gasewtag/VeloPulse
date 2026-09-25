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
from velopulse.domain.wear import (
    ActivityWearCalculationResult,
    ComponentWearDelta,
    WearThresholdExceededEvent,
)
from velopulse.domain.weather import (
    HourlyWeatherMetric,
    OpenMeteoHourlyResponse,
    OpenMeteoResponse,
    SurfaceCondition,
    WeatherEnrichmentResult,
)

__all__ = [
    "ActivityWearCalculationResult",
    "ComponentWearDelta",
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
    "WearThresholdExceededEvent",
    "WeatherEnrichmentResult",
]


