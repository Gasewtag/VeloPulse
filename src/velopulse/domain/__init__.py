"""Domain models, entities, and enums."""

from velopulse.domain.maintenance import (
    BikeMaintenanceHistory,
    ComponentReplacementResult,
    MaintenanceLogEntry,
)
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
    "BikeMaintenanceHistory",
    "ComponentReplacementResult",
    "ComponentWearDelta",
    "HourlyWeatherMetric",
    "MaintenanceLogEntry",
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
