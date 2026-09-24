"""Strava OAuth 2.0 authentication endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.session import get_db_session
from velopulse.services.strava.auth import StravaAuthService
from velopulse.services.strava.client import StravaAPIError, StravaClient

logger = logging.getLogger("velopulse.api.auth")

router = APIRouter()


def get_strava_auth_service() -> StravaAuthService:
    """Dependency injector for StravaAuthService."""
    return StravaAuthService(client=StravaClient())


@router.get(
    "/strava/authorize",
    summary="Initiate Strava OAuth 2.0 athlete authorization",
    response_model=dict[str, str],
)
async def strava_authorize(
    state: Annotated[str | None, Query(description="CSRF state token")] = None,
    redirect: Annotated[bool, Query(description="Whether to redirect immediately")] = False,
    auth_service: StravaAuthService = Depends(get_strava_auth_service),
) -> Any:
    """Generate Strava OAuth 2.0 authorization URL and optionally redirect."""
    url = auth_service.client.get_authorization_url(state=state)
    if redirect:
        return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return {"authorization_url": url}


@router.get(
    "/strava/callback",
    summary="Strava OAuth 2.0 authorization callback",
    response_model=dict[str, Any],
)
async def strava_callback(
    code: Annotated[str | None, Query(description="Temporary authorization code")] = None,
    error: Annotated[str | None, Query(description="OAuth error code returned by Strava")] = None,
    state: Annotated[
        str | None, Query(description="State parameter sent in authorize request")
    ] = None,
    scope: Annotated[str | None, Query(description="Granted scope list")] = None,
    db: AsyncSession = Depends(get_db_session),
    auth_service: StravaAuthService = Depends(get_strava_auth_service),
) -> dict[str, Any]:
    """Exchange authorization code for tokens and sync athlete profile and bikes."""
    if error:
        logger.warning("Strava authorization denied or failed with error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strava authorization failed: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'code' parameter",
        )

    try:
        user = await auth_service.authenticate_user(code=code, session=db)
    except StravaAPIError as exc:
        logger.error("Strava API error during token exchange: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Strava authentication exchange failed: {exc}",
        ) from exc

    return {
        "status": "success",
        "user_id": str(user.id),
        "strava_athlete_id": user.strava_athlete_id,
        "athlete_name": f"{user.first_name} {user.last_name or ''}".strip(),
        "bikes_imported": len(user.bikes),
        "bikes": [
            {
                "id": str(bike.id),
                "strava_gear_id": bike.strava_gear_id,
                "name": bike.name,
                "type": bike.bike_type.value,
                "total_distance_km": round(bike.total_distance_m / 1000.0, 1),
            }
            for bike in user.bikes
        ],
    }
