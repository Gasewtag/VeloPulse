"""Tests for Strava authentication and user sync service."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.core.security import decrypt_token
from velopulse.services.strava.auth import StravaAuthService
from velopulse.services.strava.client import StravaClient


@pytest.mark.asyncio
async def test_authenticate_user_creates_and_syncs_bikes(db_session: AsyncSession) -> None:
    """Verify first-time OAuth authentication creates User and imports bikes."""
    client = StravaClient()
    auth_service = StravaAuthService(client=client)

    user = await auth_service.authenticate_user(code="mock_auth_code_1", session=db_session)

    assert user.id is not None
    assert user.strava_athlete_id == 987654321
    assert user.first_name == "Alex"
    assert user.last_name == "Rider"
    assert user.access_token.startswith("mock_access_")

    # Verify refresh token is securely encrypted in database
    assert not user.refresh_token.startswith("mock_refresh_")
    decrypted_refresh = decrypt_token(user.refresh_token)
    assert decrypted_refresh.startswith("mock_refresh_")

    # Verify bikes imported
    assert len(user.bikes) == 2
    road_bike = next(b for b in user.bikes if "Tarmac" in b.name)
    assert road_bike.strava_gear_id == "b1234567"
    assert road_bike.total_distance_m == 1250000


@pytest.mark.asyncio
async def test_authenticate_user_updates_existing_cyclist(db_session: AsyncSession) -> None:
    """Verify subsequent login updates existing athlete record rather than duplicating."""
    client = StravaClient()
    auth_service = StravaAuthService(client=client)

    # 1. Initial auth
    user1 = await auth_service.authenticate_user(code="mock_auth_code_1", session=db_session)
    user1_id = user1.id

    # 2. Subsequent auth with updated code
    user2 = await auth_service.authenticate_user(code="mock_auth_code_2", session=db_session)

    assert user2.id == user1_id
    assert user2.strava_athlete_id == 987654321
    assert len(user2.bikes) == 2


@pytest.mark.asyncio
async def test_get_valid_access_token_expiry_handling(db_session: AsyncSession) -> None:
    """Verify token auto-refreshes when within 5 minutes of expiration."""
    client = StravaClient()
    auth_service = StravaAuthService(client=client)

    user = await auth_service.authenticate_user(code="mock_auth_code_expire", session=db_session)
    original_access = user.access_token

    # Case 1: Token is fresh (valid for next 5 hours) -> no refresh
    valid_token = await auth_service.get_valid_access_token(user, session=db_session)
    assert valid_token == original_access

    # Case 2: Token is expired or expiring within 3 minutes
    user.token_expires_at = datetime.now(UTC) + timedelta(minutes=2)
    await db_session.commit()

    refreshed_token = await auth_service.get_valid_access_token(user, session=db_session)
    assert refreshed_token != original_access
    assert refreshed_token.startswith("mock_refreshed_access_")
    assert user.access_token == refreshed_token
