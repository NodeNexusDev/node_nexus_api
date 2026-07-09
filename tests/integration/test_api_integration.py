"""Integration tests for API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_check_integration(client):
    """Test health check endpoint integration."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
