"""Tests for API endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_get_nodes(client):
    """Test get nodes endpoint."""
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.get_all_nodes = AsyncMock(return_value=[])
        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        assert response.json() == []


def test_create_node(client):
    """Test create node endpoint."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.create_node = AsyncMock(
            return_value={
                "id": node_id,
                "name": "test-node",
                "host": "192.168.1.100",
                "port": 22,
                "connection_type": "ssh",
                "status": "active",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        )
        response = client.post(
            "/api/v1/nodes",
            json={
                "name": "test-node",
                "host": "192.168.1.100",
                "connection_type": "ssh",
            },
        )
        assert response.status_code == 201
        assert response.json()["name"] == "test-node"
