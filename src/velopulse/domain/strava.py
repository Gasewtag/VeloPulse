"""Strava domain schemas and data transfer objects."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from velopulse.db.models.enums import BikeType


class StravaGearSummary(BaseModel):
    """Summary of bicycle gear registered to an athlete profile."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    primary: bool = False
    distance: float = 0.0  # meters
    resource_state: int = 2

    def infer_bike_type(self) -> BikeType:
        """Infer BikeType enumeration from gear name using heuristic matching."""
        lower_name = self.name.lower()
        if any(keyword in lower_name for keyword in ["gravel", "gvl", "diverge", "grail", "grizl"]):
            return BikeType.GRAVEL
        if any(
            keyword in lower_name
            for keyword in ["mtb", "mountain", "enduro", "trail", "xc", "epic", "stumpjumper"]
        ):
            return BikeType.MTB
        if any(
            keyword in lower_name
            for keyword in ["ebike", "e-bike", "electric", "turbo", "creo", "levo"]
        ):
            return BikeType.EBIKE
        if any(keyword in lower_name for keyword in ["commute", "city", "hybrid", "town"]):
            return BikeType.COMMUTER
        if any(
            keyword in lower_name
            for keyword in ["tt", "time trial", "triathlon", "shiv", "speedmax"]
        ):
            return BikeType.TT
        return BikeType.ROAD


class StravaAthleteSummary(BaseModel):
    """Summary representation of athlete profile returned during OAuth."""

    model_config = ConfigDict(extra="ignore")

    id: int
    username: str | None = None
    firstname: str
    lastname: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    profile_medium: str | None = None
    bikes: list[StravaGearSummary] = Field(default_factory=list)


class StravaTokenResponse(BaseModel):
    """OAuth 2.0 authorization code token exchange payload."""

    model_config = ConfigDict(extra="ignore")

    token_type: str = "Bearer"
    access_token: str
    expires_at: int  # Epoch seconds
    expires_in: int
    refresh_token: str
    athlete: StravaAthleteSummary | None = None


class StravaRefreshTokenResponse(BaseModel):
    """OAuth 2.0 refresh token renewal response payload."""

    model_config = ConfigDict(extra="ignore")

    token_type: str = "Bearer"
    access_token: str
    expires_at: int
    expires_in: int
    refresh_token: str


class StravaWebhookChallenge(BaseModel):
    """Incoming Strava webhook GET handshake challenge query parameters."""

    model_config = ConfigDict(populate_by_name=True)

    hub_mode: str = Field(alias="hub.mode")
    hub_challenge: str = Field(alias="hub.challenge")
    hub_verify_token: str = Field(alias="hub.verify_token")


class StravaWebhookChallengeResponse(BaseModel):
    """Outgoing Strava webhook GET handshake validation payload."""

    model_config = ConfigDict(populate_by_name=True)

    hub_challenge: str = Field(serialization_alias="hub.challenge")


class StravaWebhookEvent(BaseModel):
    """Real-time Strava push event notification payload."""

    model_config = ConfigDict(extra="ignore")

    object_type: Literal["activity", "athlete"]
    object_id: int
    aspect_type: Literal["create", "update", "delete"]
    owner_id: int
    subscription_id: int
    event_time: int
    updates: dict[str, Any] = Field(default_factory=dict)


class StravaSubscription(BaseModel):
    """Webhook subscription descriptor registered with Strava API."""

    model_config = ConfigDict(extra="ignore")

    id: int
    application_id: int
    callback_url: str
    created_at: datetime
    updated_at: datetime


class StravaActivityDetailed(BaseModel):
    """Detailed activity information from Strava."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    distance: float
    moving_time: int
    total_elevation_gain: float
    type: str
    sport_type: str
    start_date: datetime
    start_latlng: list[float] | None = None
    gear_id: str | None = None
