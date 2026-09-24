"""Smoke test for system health probe endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_200(async_client: AsyncClient) -> None:
    """Ensure GET /health returns 200 OK with correct payload structure."""
    response = await async_client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "VeloPulse"
    assert "version" in data
    assert "environment" in data
