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


def _make_node_response(node_id: uuid.UUID | None = None) -> dict:
    """Create a node response dict."""
    return {
        "id": node_id or uuid.uuid4(),
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }


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


def test_get_nodes_with_data(client):
    """Test get nodes endpoint with data."""
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.get_all_nodes = AsyncMock(
            return_value=[_make_node_response(), _make_node_response()]
        )
        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        assert len(response.json()) == 2


def test_get_node_found(client):
    """Test get single node endpoint when found."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.get_node = AsyncMock(
            return_value=_make_node_response(node_id)
        )
        response = client.get(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(node_id)


def test_get_node_not_found(client):
    """Test get single node endpoint when not found."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        from app.core.exceptions import NodeNotFoundError

        mock_service.return_value.get_node = AsyncMock(
            side_effect=NodeNotFoundError()
        )
        response = client.get(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 404


def test_create_node(client):
    """Test create node endpoint."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.create_node = AsyncMock(
            return_value=_make_node_response(node_id)
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


def test_update_node_found(client):
    """Test update node endpoint when found."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.update_node = AsyncMock(
            return_value=_make_node_response(node_id)
        )
        response = client.put(
            f"/api/v1/nodes/{node_id}",
            json={"name": "updated-node"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "test-node"


def test_update_node_not_found(client):
    """Test update node endpoint when not found."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        from app.core.exceptions import NodeNotFoundError

        mock_service.return_value.update_node = AsyncMock(
            side_effect=NodeNotFoundError()
        )
        response = client.put(
            f"/api/v1/nodes/{node_id}",
            json={"name": "updated-node"},
        )
        assert response.status_code == 404


def test_delete_node_found(client):
    """Test delete node endpoint when found."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.delete_node = AsyncMock(return_value=True)
        response = client.delete(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 204


def test_delete_node_not_found(client):
    """Test delete node endpoint when not found."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        from app.core.exceptions import NodeNotFoundError

        mock_service.return_value.delete_node = AsyncMock(
            side_effect=NodeNotFoundError()
        )
        response = client.delete(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 404
