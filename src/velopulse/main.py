"""FastAPI main application entrypoint."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from velopulse import __version__
from velopulse.api.v1.router import api_router
from velopulse.core.config import get_settings
from velopulse.core.logging import setup_logging
from velopulse.db.session import dispose_engine, engine
from velopulse.observability import (
    SYSTEM_HEALTH_STATUS,
    CorrelationIdMiddleware,
    PrometheusMetricsMiddleware,
    get_metrics_payload,
    update_queue_backlog_metrics,
)

settings = get_settings()
setup_logging(debug=settings.DEBUG, log_format=settings.LOG_FORMAT)
logger = logging.getLogger("velopulse.health")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown events."""
    logger.info(
        "Starting up VeloPulse application (v%s, env=%s)", __version__, settings.ENVIRONMENT
    )
    yield
    logger.info("Shutting down VeloPulse application")
    await dispose_engine()


def create_application() -> FastAPI:
    """Application factory for VeloPulse."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=__version__,
        description="Automated bicycle component wear tracker, maintenance scheduler, and cycling assistant.",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS Middleware configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Observability Middlewares
    if settings.PROMETHEUS_ENABLED:
        app.add_middleware(PrometheusMetricsMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # Base Health Check Route
    @app.get("/health", tags=["Health"], summary="System health probe")
    async def health_check() -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        checks: dict[str, str] = {
            "database": "unknown",
            "redis": "unknown",
        }

        # 1. Probe PostgreSQL reachability using shared engine pool
        try:
            async with asyncio.timeout(2.0):
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            checks["database"] = "connected"
        except Exception as exc:
            logger.warning("Database probe failed: %s", exc)
            checks["database"] = "unavailable"

        # 2. Probe Redis reachability
        try:
            redis_client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2.0)
            async with asyncio.timeout(2.0):
                await redis_client.ping()
            await redis_client.aclose()
            checks["redis"] = "connected"
        except Exception as exc:
            logger.warning("Redis probe failed: %s", exc)
            checks["redis"] = "unavailable"

        is_healthy = all(status == "connected" for status in checks.values())
        overall_status = "healthy" if is_healthy else "degraded"

        # Update Prometheus health gauges
        SYSTEM_HEALTH_STATUS.labels(component="database").set(
            1.0 if checks["database"] == "connected" else 0.0
        )
        SYSTEM_HEALTH_STATUS.labels(component="redis").set(
            1.0 if checks["redis"] == "connected" else 0.0
        )

        logger.info(
            "Health probe [%s]: database=%s, redis=%s, overall=%s",
            timestamp,
            checks["database"],
            checks["redis"],
            overall_status,
        )

        return {
            "status": overall_status,
            "timestamp": timestamp,
            "project": settings.PROJECT_NAME,
            "version": __version__,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
        }

    # Prometheus Metrics Exposition Endpoint
    @app.get(
        "/metrics",
        tags=["Observability"],
        summary="Prometheus telemetry and metrics",
        response_class=Response,
    )
    async def metrics_endpoint() -> Response:
        try:
            redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
            await update_queue_backlog_metrics(redis_client)
            await redis_client.aclose()
        except Exception as exc:
            logger.debug("Failed updating queue metrics during scrape: %s", exc)

        payload, content_type = get_metrics_payload()
        return Response(content=payload, media_type=content_type)

    # Mount API v1 router
    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app


app = create_application()
