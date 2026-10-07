"""Tests for Strava API client."""

import httpx
import pytest
import respx

from velopulse.core.config import Settings
from velopulse.domain.strava import StravaTokenResponse
from velopulse.services.strava.client import StravaAPIError, StravaClient


@pytest.fixture
def mock_settings() -> Settings:
    """Provide settings with test credentials."""
    return Settings(
        STRAVA_MOCK_MODE=True,
        STRAVA_CLIENT_ID="123456",
        STRAVA_CLIENT_SECRET="secret789",
        STRAVA_VERIFY_TOKEN="test_verify_token",
        STRAVA_WEBHOOK_CALLBACK_URL="https://example.com/api/v1/webhooks/strava",
    )


def test_authorization_url_generation(mock_settings: Settings) -> None:
    """Verify authorization URL matches Strava OAuth specification."""
    client = StravaClient(settings=mock_settings)
    url = client.get_authorization_url(state="csrf_abc_123")

    assert "https://www.strava.com/oauth/authorize" in url
    assert "client_id=123456" in url
    assert "response_type=code" in url
    assert (
        "scope=read%2Cactivity%3Aread_all%2Cprofile%3Aread_all" in url
        or "scope=read,activity:read_all,profile:read_all" in url
    )
    assert "state=csrf_abc_123" in url


@pytest.mark.asyncio
async def test_exchange_code_mock_mode(mock_settings: Settings) -> None:
    """Verify mock mode returns high-fidelity athlete and bike objects offline."""
    client = StravaClient(settings=mock_settings)
    result = await client.exchange_code_for_token("mock_code_test")

    assert isinstance(result, StravaTokenResponse)
    assert result.access_token.startswith("mock_access_")
    assert result.refresh_token.startswith("mock_refresh_")
    assert result.athlete is not None
    assert result.athlete.id == 987654321
    assert len(result.athlete.bikes) == 2
    assert result.athlete.bikes[0].name == "Specialized Tarmac SL7 (Road)"


@pytest.mark.asyncio
async def test_refresh_token_mock_mode(mock_settings: Settings) -> None:
    """Verify mock mode token refresh returns refreshed credentials offline."""
    client = StravaClient(settings=mock_settings)
    result = await client.refresh_access_token("mock_refresh_old_123")

    assert result.access_token.startswith("mock_refreshed_access_")
    assert result.refresh_token.startswith("mock_refreshed_token_")
    assert result.expires_in == 21600


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_live_mode_success() -> None:
    """Verify live mode HTTP code exchange against Strava token endpoint."""
    live_settings = Settings(
        STRAVA_MOCK_MODE=False,
        STRAVA_CLIENT_ID="99999",
        STRAVA_CLIENT_SECRET="live_secret",
    )
    client = StravaClient(settings=live_settings)

    mock_route = respx.post("https://www.strava.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "access_token": "live_access_token_xyz",
                "expires_at": 1750000000,
                "expires_in": 21600,
                "refresh_token": "live_refresh_token_abc",
                "athlete": {
                    "id": 11223344,
                    "firstname": "Chris",
                    "lastname": "Froome",
                    "bikes": [
                        {
                            "id": "b999",
                            "name": "Pinarello Dogma F",
                            "primary": True,
                            "distance": 500000.0,
                        }
                    ],
                },
            },
        )
    )

    result = await client.exchange_code_for_token("real_auth_code")
    assert mock_route.called
    assert result.access_token == "live_access_token_xyz"
    assert result.athlete is not None
    assert result.athlete.id == 11223344
    assert len(result.athlete.bikes) == 1


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_live_mode_error() -> None:
    """Verify StravaAPIError is raised when Strava returns 400 Bad Request."""
    live_settings = Settings(
        STRAVA_MOCK_MODE=False,
        STRAVA_CLIENT_ID="99999",
        STRAVA_CLIENT_SECRET="live_secret",
    )
    client = StravaClient(settings=live_settings)

    respx.post("https://www.strava.com/oauth/token").mock(
        return_value=httpx.Response(
            400,
            json={"message": "Bad Request", "errors": [{"field": "code", "code": "invalid"}]},
        )
    )

    with pytest.raises(StravaAPIError) as exc_info:
        await client.exchange_code_for_token("invalid_code")

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
@respx.mock
async def test_webhook_subscription_lifecycle() -> None:
    """Verify Strava push subscription create, list, and delete methods."""
    live_settings = Settings(
        STRAVA_MOCK_MODE=False,
        STRAVA_CLIENT_ID="12345",
        STRAVA_CLIENT_SECRET="secret54321",
        STRAVA_VERIFY_TOKEN="my_verify_token",
        STRAVA_WEBHOOK_CALLBACK_URL="https://example.com/api/v1/webhooks/strava",
    )
    client = StravaClient(settings=live_settings)

    # 1. Create subscription
    respx.post("https://www.strava.com/api/v3/push_subscriptions").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 1001,
                "application_id": 12345,
                "callback_url": "https://example.com/api/v1/webhooks/strava",
                "created_at": "2026-09-24T12:00:00Z",
                "updated_at": "2026-09-24T12:00:00Z",
            },
        )
    )
    sub = await client.create_subscription()
    assert sub.id == 1001
    assert sub.application_id == 12345

    # 2. List subscriptions
    respx.get("https://www.strava.com/api/v3/push_subscriptions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1001,
                    "application_id": 12345,
                    "callback_url": "https://example.com/api/v1/webhooks/strava",
                    "created_at": "2026-09-24T12:00:00Z",
                    "updated_at": "2026-09-24T12:00:00Z",
                }
            ],
        )
    )
    subs = await client.list_subscriptions()
    assert len(subs) == 1
    assert subs[0].id == 1001

    # 3. Delete subscription
    respx.delete("https://www.strava.com/api/v3/push_subscriptions/1001").mock(
        return_value=httpx.Response(204)
    )
    await client.delete_subscription(1001)


@pytest.mark.asyncio
@respx.mock
async def test_live_token_refresh_and_errors() -> None:
    """Verify live mode token refresh success and error handling."""
    live_settings = Settings(
        STRAVA_MOCK_MODE=False,
        STRAVA_CLIENT_ID="99999",
        STRAVA_CLIENT_SECRET="live_secret",
    )
    client = StravaClient(settings=live_settings)

    # Success
    respx.post("https://www.strava.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "refreshed_live_token",
                "refresh_token": "new_refresh_token",
                "expires_at": 1800000000,
                "expires_in": 21600,
                "token_type": "Bearer",
            },
        )
    )
    ref = await client.refresh_access_token("valid_refresh_token")
    assert ref.access_token == "refreshed_live_token"

    # Error
    respx.post("https://www.strava.com/oauth/token").mock(
        return_value=httpx.Response(400, text="Bad Request")
    )
    with pytest.raises(StravaAPIError):
        await client.refresh_access_token("bad_token")


@pytest.mark.asyncio
@respx.mock
async def test_live_get_athlete_profile_and_errors() -> None:
    """Verify live get_athlete_profile success and error handling."""
    live_settings = Settings(STRAVA_MOCK_MODE=False)
    client = StravaClient(settings=live_settings)

    # Success
    respx.get("https://www.strava.com/api/v3/athlete").mock(
        return_value=httpx.Response(
            200,
            json={"id": 8888, "firstname": "Wout", "lastname": "van Aert", "bikes": []},
        )
    )
    athlete = await client.get_athlete_profile("valid_tok")
    assert athlete.id == 8888
    assert athlete.firstname == "Wout"

    # Error
    respx.get("https://www.strava.com/api/v3/athlete").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    with pytest.raises(StravaAPIError):
        await client.get_athlete_profile("invalid_tok")


@pytest.mark.asyncio
@respx.mock
async def test_live_get_activity_and_delete_error() -> None:
    """Verify live get_activity success, error, and delete_subscription error."""
    live_settings = Settings(STRAVA_MOCK_MODE=False)
    client = StravaClient(settings=live_settings)

    # Activity Success
    respx.get("https://www.strava.com/api/v3/activities/12345").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 12345,
                "name": "Morning Ride",
                "distance": 32000.0,
                "moving_time": 4200,
                "total_elevation_gain": 350.0,
                "type": "Ride",
                "sport_type": "Ride",
                "start_date": "2026-09-24T08:00:00Z",
                "start_latlng": [45.0, 9.0],
                "gear_id": "b111",
            },
        )
    )
    act = await client.get_activity("token", 12345)
    assert act.id == 12345
    assert act.distance == 32000.0

    # Activity Error
    respx.get("https://www.strava.com/api/v3/activities/99999").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    with pytest.raises(StravaAPIError):
        await client.get_activity("token", 99999)

    # Delete Subscription Error
    respx.delete("https://www.strava.com/api/v3/push_subscriptions/555").mock(
        return_value=httpx.Response(500, text="Server Error")
    )
    with pytest.raises(StravaAPIError):
        await client.delete_subscription(555)
