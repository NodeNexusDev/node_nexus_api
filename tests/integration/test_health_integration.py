"""Integration tests for health check endpoints."""

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check_integration() -> None:
    """GET /health returns healthy in integration environment."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_health_check_no_auth_integration() -> None:
    """GET /health works without authentication in integration."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
