"""API v1 master router."""

from fastapi import APIRouter

api_router = APIRouter()

# Future routers will be mounted here:
# api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
# api_router.include_router(bikes.router, prefix="/bikes", tags=["bikes"])
# api_router.include_router(components.router, prefix="/components", tags=["components"])
