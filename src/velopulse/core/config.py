"""Application settings and runtime configuration."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings validated with Pydantic."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # General App Config
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "VeloPulse"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "temporary-dev-secret-key-change-in-production-min-32-bytes"

    # Server Binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # PostgreSQL Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "velopulse_user"
    POSTGRES_PASSWORD: str = "velopulse_password"
    POSTGRES_DB: str = "velopulse_db"
    POSTGRES_ECHO: bool = False

    # Redis Broker & Cache
    REDIS_URL: str = "redis://localhost:6379/0"

    # Strava API Credentials
    STRAVA_CLIENT_ID: str = ""
    STRAVA_CLIENT_SECRET: str = ""
    STRAVA_VERIFY_TOKEN: str = ""
    STRAVA_WEBHOOK_CALLBACK_URL: str = ""

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""

    # Open-Meteo Weather API
    OPEN_METEO_BASE_URL: str = "https://archive-api.open-meteo.com/v1/archive"

    @property
    def async_postgres_dsn(self) -> str:
        """Construct async PostgreSQL connection string."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_postgres_dsn(self) -> str:
        """Construct sync PostgreSQL connection string for Alembic migrations."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
