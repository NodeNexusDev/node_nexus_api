"""Tests for API endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client with lifespan support."""
    with TestClient(app) as c:
        yield c


def _create_node(client: TestClient, **overrides) -> dict:
    """Helper to create a node and return the response."""
    data = {
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        **overrides,
    }
    response = client.post("/api/v1/nodes", json=data)
    assert response.status_code == 201
    return response.json()


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_get_nodes_empty(client):
    """Test get nodes endpoint with empty database."""
    response = client.get("/api/v1/nodes")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_nodes_with_data(client):
    """Test get nodes endpoint returns created nodes."""
    _create_node(client, name="node-1")
    _create_node(client, name="node-2")

    response = client.get("/api/v1/nodes")
    assert response.status_code == 200
    nodes = response.json()
    assert len(nodes) >= 2


def test_get_node_found(client):
    """Test get single node endpoint when found."""
    node = _create_node(client)
    node_id = node["id"]

    response = client.get(f"/api/v1/nodes/{node_id}")
    assert response.status_code == 200
    assert response.json()["id"] == node_id
    assert response.json()["name"] == "test-node"


def test_get_node_not_found(client):
    """Test get single node endpoint when not found."""
    response = client.get(f"/api/v1/nodes/{uuid.uuid4()}")
    assert response.status_code == 404


def test_create_node(client):
    """Test create node endpoint."""
    response = client.post(
        "/api/v1/nodes",
        json={
            "name": "new-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "new-node"
    assert data["host"] == "10.0.0.1"
    assert "id" in data


def test_update_node_found(client):
    """Test update node endpoint when found."""
    node = _create_node(client)
    node_id = node["id"]

    response = client.put(
        f"/api/v1/nodes/{node_id}",
        json={"name": "updated-node"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "updated-node"
    assert response.json()["id"] == node_id


def test_update_node_not_found(client):
    """Test update node endpoint when not found."""
    response = client.put(
        f"/api/v1/nodes/{uuid.uuid4()}",
        json={"name": "updated-node"},
    )
    assert response.status_code == 404


def test_delete_node_found(client):
    """Test delete node endpoint when found."""
    node = _create_node(client)
    node_id = node["id"]

    response = client.delete(f"/api/v1/nodes/{node_id}")
    assert response.status_code == 204

    response = client.get(f"/api/v1/nodes/{node_id}")
    assert response.status_code == 404


def test_delete_node_not_found(client):
    """Test delete node endpoint when not found."""
    response = client.delete(f"/api/v1/nodes/{uuid.uuid4()}")
    assert response.status_code == 404
