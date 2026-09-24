"""API v1 master router."""

from fastapi import APIRouter

from velopulse.api.v1.auth import router as auth_router
from velopulse.api.v1.webhooks import router as webhooks_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
