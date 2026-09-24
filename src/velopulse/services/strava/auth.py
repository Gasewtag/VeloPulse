"""Strava OAuth 2.0 authentication and user synchronization service."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from velopulse.core.security import decrypt_token, encrypt_token
from velopulse.db.models.bike import Bike
from velopulse.db.models.user import User
from velopulse.domain.strava import StravaTokenResponse
from velopulse.services.strava.client import StravaClient

logger = logging.getLogger("velopulse.strava.auth")


class StravaAuthService:
    """Orchestrates Strava OAuth handshake and athlete data persistence."""

    def __init__(self, client: StravaClient | None = None) -> None:
        self.client = client or StravaClient()

    async def authenticate_user(
        self,
        code: str,
        session: AsyncSession,
    ) -> User:
        """Exchange authorization code and persist or update athlete record and bikes."""
        token_resp: StravaTokenResponse = await self.client.exchange_code_for_token(code)

        athlete = token_resp.athlete
        if athlete is None:
            # If token response did not embed athlete, fetch explicitly
            athlete = await self.client.get_athlete_profile(token_resp.access_token)

        expires_at = datetime.fromtimestamp(token_resp.expires_at, tz=UTC)
        encrypted_refresh = encrypt_token(token_resp.refresh_token)

        # 1. Lookup or create User
        query = (
            select(User)
            .where(User.strava_athlete_id == athlete.id)
            .options(selectinload(User.bikes))
        )
        result = await session.execute(query)
        user = result.scalars().first()

        now = datetime.now(UTC)
        existing_bikes: dict[str, Bike] = {}

        if user is None:
            logger.info("Registering new cyclist from Strava athlete id: %s", athlete.id)
            user = User(
                strava_athlete_id=athlete.id,
                first_name=athlete.firstname,
                last_name=athlete.lastname,
                access_token=token_resp.access_token,
                refresh_token=encrypted_refresh,
                token_expires_at=expires_at,
                last_synced_at=now,
            )
            session.add(user)
            await session.flush()
        else:
            logger.info("Updating existing cyclist from Strava athlete id: %s", athlete.id)
            user.first_name = athlete.firstname
            user.last_name = athlete.lastname
            user.access_token = token_resp.access_token
            user.refresh_token = encrypted_refresh
            user.token_expires_at = expires_at
            user.last_synced_at = now
            bike_query = select(Bike).where(Bike.user_id == user.id)
            bike_result = await session.execute(bike_query)
            existing_bikes = {b.strava_gear_id: b for b in bike_result.scalars().all()}

        # 2. Synchronize athlete bikes/gear
        for gear in athlete.bikes:
            inferred_type = gear.infer_bike_type()
            distance_int = int(gear.distance)

            if gear.id in existing_bikes:
                bike = existing_bikes[gear.id]
                bike.name = gear.name
                bike.bike_type = inferred_type
                bike.total_distance_m = distance_int
                bike.is_active = True
            else:
                logger.info("Importing gear '%s' (%s) for user %s", gear.name, gear.id, user.id)
                new_bike = Bike(
                    user_id=user.id,
                    strava_gear_id=gear.id,
                    name=gear.name,
                    bike_type=inferred_type,
                    total_distance_m=distance_int,
                    is_active=True,
                )
                session.add(new_bike)

        await session.commit()
        fetch_stmt = select(User).where(User.id == user.id).options(selectinload(User.bikes))
        loaded_res = await session.execute(fetch_stmt)
        return loaded_res.scalar_one()

    async def get_valid_access_token(
        self,
        user: User,
        session: AsyncSession,
    ) -> str:
        """Retrieve valid Strava access token, refreshing if within 5-minute expiry threshold."""
        now = datetime.now(UTC)
        # Check if expired or within 5 minutes of expiring
        if now >= (user.token_expires_at - timedelta(minutes=5)):
            logger.info("Strava access token expired/expiring for user %s. Refreshing...", user.id)
            plaintext_refresh = decrypt_token(user.refresh_token)
            refreshed = await self.client.refresh_access_token(plaintext_refresh)

            user.access_token = refreshed.access_token
            user.refresh_token = encrypt_token(refreshed.refresh_token)
            user.token_expires_at = datetime.fromtimestamp(refreshed.expires_at, tz=UTC)

            await session.commit()
            return user.access_token

        return user.access_token
