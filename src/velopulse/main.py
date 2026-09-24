"""FastAPI main application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from velopulse import __version__
from velopulse.api.v1.router import api_router
from velopulse.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown events."""
    # Startup actions (e.g. initialize connection pools, taskiq broker)
    yield
    # Shutdown actions (e.g. close pools, disconnect clients)


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

    # Base Health Check Route
    @app.get("/health", tags=["Health"], summary="System health probe")
    async def health_check() -> dict[str, Any]:
        return {
            "status": "healthy",
            "project": settings.PROJECT_NAME,
            "version": __version__,
            "environment": settings.ENVIRONMENT,
        }

    # Mount API v1 router
    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app


app = create_application()
