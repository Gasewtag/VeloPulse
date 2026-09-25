"""HTTP client interfacing with Strava OAuth 2.0 and REST API v3."""

import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from velopulse.core.config import Settings, get_settings
from velopulse.domain.strava import (
    StravaActivityDetailed,
    StravaAthleteSummary,
    StravaGearSummary,
    StravaRefreshTokenResponse,
    StravaSubscription,
    StravaTokenResponse,
)

logger = logging.getLogger("velopulse.strava.client")


class StravaAPIError(Exception):
    """Exception raised when Strava API interaction fails."""

    def __init__(
        self, message: str, status_code: int | None = None, response_body: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class StravaClient:
    """Asynchronous client for Strava OAuth and Webhook administration."""

    STRAVA_OAUTH_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
    STRAVA_OAUTH_TOKEN_URL = "https://www.strava.com/oauth/token"
    STRAVA_API_BASE_URL = "https://www.strava.com/api/v3"
    REQUIRED_SCOPES = "read,activity:read_all,profile:read_all"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_authorization_url(
        self, state: str | None = None, redirect_uri: str | None = None
    ) -> str:
        """Construct the Strava OAuth 2.0 athlete authorization redirect URL."""
        params = {
            "client_id": self.settings.STRAVA_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri
            or self.settings.STRAVA_WEBHOOK_CALLBACK_URL.replace(
                "/webhooks/strava", "/auth/strava/callback"
            ),
            "approval_prompt": "auto",
            "scope": self.REQUIRED_SCOPES,
        }
        if state:
            params["state"] = state
        return f"{self.STRAVA_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> StravaTokenResponse:
        """Exchange authorization code for OAuth access and refresh tokens."""
        # Offline sandbox fallback
        if self.settings.STRAVA_MOCK_MODE and (code.startswith("mock_") or code == "dev_code_123"):
            logger.info("Serving synthetic Strava token exchange for mock code: %s", code)
            now = int(time.time())
            return StravaTokenResponse(
                token_type="Bearer",
                access_token=f"mock_access_{code}_{now}",
                expires_at=now + 21600,
                expires_in=21600,
                refresh_token=f"mock_refresh_{code}_{now}",
                athlete=StravaAthleteSummary(
                    id=987654321,
                    username="velopulse_tester",
                    firstname="Alex",
                    lastname="Rider",
                    city="San Francisco",
                    state="California",
                    country="United States",
                    bikes=[
                        StravaGearSummary(
                            id="b1234567",
                            name="Specialized Tarmac SL7 (Road)",
                            primary=True,
                            distance=1250000.0,
                        ),
                        StravaGearSummary(
                            id="b7654321",
                            name="Canyon Grizl CF SL (Gravel)",
                            primary=False,
                            distance=450000.0,
                        ),
                    ],
                ),
            )

        payload = {
            "client_id": self.settings.STRAVA_CLIENT_ID,
            "client_secret": self.settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.STRAVA_OAUTH_TOKEN_URL, data=payload)
            if response.status_code != 200:
                logger.error(
                    "Strava code exchange failed: %d - %s",
                    response.status_code,
                    response.text,
                )
                raise StravaAPIError(
                    f"Failed to exchange code: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            return StravaTokenResponse.model_validate(response.json())

    async def refresh_access_token(self, refresh_token: str) -> StravaRefreshTokenResponse:
        """Refresh expired access token using stored refresh token."""
        # Offline sandbox fallback
        if self.settings.STRAVA_MOCK_MODE:
            logger.info("Serving synthetic Strava token refresh for mock token")
            now = int(time.time())
            return StravaRefreshTokenResponse(
                token_type="Bearer",
                access_token=f"mock_refreshed_access_{now}",
                expires_at=now + 21600,
                expires_in=21600,
                refresh_token=f"mock_refreshed_token_{now}",
            )

        payload = {
            "client_id": self.settings.STRAVA_CLIENT_ID,
            "client_secret": self.settings.STRAVA_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.STRAVA_OAUTH_TOKEN_URL, data=payload)
            if response.status_code != 200:
                logger.error(
                    "Strava token refresh failed: %d - %s",
                    response.status_code,
                    response.text,
                )
                raise StravaAPIError(
                    f"Failed to refresh token: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            return StravaRefreshTokenResponse.model_validate(response.json())

    async def get_athlete_profile(self, access_token: str) -> StravaAthleteSummary:
        """Fetch current athlete profile including associated bike gear."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.STRAVA_API_BASE_URL}/athlete"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise StravaAPIError(
                    f"Failed to fetch athlete profile: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            return StravaAthleteSummary.model_validate(response.json())

    async def list_subscriptions(self) -> list[StravaSubscription]:
        """View all active webhook subscriptions for the application."""
        params = {
            "client_id": self.settings.STRAVA_CLIENT_ID,
            "client_secret": self.settings.STRAVA_CLIENT_SECRET,
        }
        url = f"{self.STRAVA_API_BASE_URL}/push_subscriptions"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                raise StravaAPIError(
                    f"Failed to list subscriptions: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            items = response.json()
            return [StravaSubscription.model_validate(sub) for sub in items]

    async def create_subscription(
        self,
        callback_url: str | None = None,
        verify_token: str | None = None,
    ) -> StravaSubscription:
        """Register a new webhook push subscription with Strava."""
        target_callback = callback_url or self.settings.STRAVA_WEBHOOK_CALLBACK_URL
        target_verify = verify_token or self.settings.STRAVA_VERIFY_TOKEN

        payload = {
            "client_id": self.settings.STRAVA_CLIENT_ID,
            "client_secret": self.settings.STRAVA_CLIENT_SECRET,
            "callback_url": target_callback,
            "verify_token": target_verify,
        }
        url = f"{self.STRAVA_API_BASE_URL}/push_subscriptions"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=payload)
            if response.status_code not in (200, 201):
                raise StravaAPIError(
                    f"Failed to create subscription: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            return StravaSubscription.model_validate(response.json())

    async def delete_subscription(self, subscription_id: int) -> None:
        """Delete an active webhook push subscription from Strava."""
        params = {
            "client_id": self.settings.STRAVA_CLIENT_ID,
            "client_secret": self.settings.STRAVA_CLIENT_SECRET,
        }
        url = f"{self.STRAVA_API_BASE_URL}/push_subscriptions/{subscription_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(url, params=params)
            if response.status_code not in (200, 204):
                raise StravaAPIError(
                    f"Failed to delete subscription: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )

    async def get_activity(self, access_token: str, activity_id: int) -> StravaActivityDetailed:
        """Fetch detailed activity from Strava API."""
        if self.settings.STRAVA_MOCK_MODE:
            logger.info("Serving synthetic Strava activity for mock activity_id: %d", activity_id)
            return StravaActivityDetailed(
                id=activity_id,
                name="Mock Ride",
                distance=25000.0,
                moving_time=3600,
                total_elevation_gain=250.0,
                type="Ride",
                sport_type="Ride",
                start_date=datetime.now(UTC),
                start_latlng=[37.7749, -122.4194],
                gear_id="b1234567",
            )

        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.STRAVA_API_BASE_URL}/activities/{activity_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise StravaAPIError(
                    f"Failed to fetch activity: {response.text}",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            return StravaActivityDetailed.model_validate(response.json())
