"""Tests for API endpoints. Require running PostgreSQL via Docker."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker


async def _create_node(client: AsyncClient, **overrides) -> dict:
    """Helper to create a node and return the response."""
    data = {
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        **overrides,
    }
    response = await client.post("/api/v1/nodes", json=data)
    assert response.status_code == 201
    return response.json()


async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test_get_nodes_empty(client: AsyncClient):
    """Test get nodes endpoint with empty database."""
    response = await client.get("/api/v1/nodes")
    assert response.status_code == 200


async def test_get_nodes_with_data(client: AsyncClient):
    """Test get nodes endpoint returns created nodes."""
    await _create_node(client, name="node-1")
    await _create_node(client, name="node-2")

    response = await client.get("/api/v1/nodes")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


async def test_get_node_found(client: AsyncClient):
    """Test get single node endpoint when found."""
    node = await _create_node(client)
    node_id = node["id"]

    response = await client.get(f"/api/v1/nodes/{node_id}")
    assert response.status_code == 200
    assert response.json()["id"] == node_id
    assert response.json()["name"] == "test-node"


async def test_get_node_not_found(client: AsyncClient):
    """Test get single node endpoint when not found."""
    response = await client.get(f"/api/v1/nodes/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_create_node(client: AsyncClient):
    """Test create node endpoint."""
    response = await client.post(
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


async def test_update_node_found(client: AsyncClient):
    """Test update node endpoint when found."""
    node = await _create_node(client)
    node_id = node["id"]

    response = await client.put(
        f"/api/v1/nodes/{node_id}",
        json={"name": "updated-node"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "updated-node"
    assert response.json()["id"] == node_id


async def test_update_node_not_found(client: AsyncClient):
    """Test update node endpoint when not found."""
    response = await client.put(
        f"/api/v1/nodes/{uuid.uuid4()}",
        json={"name": "updated-node"},
    )
    assert response.status_code == 404


async def test_delete_node_found(client: AsyncClient):
    """Test delete node endpoint when found."""
    node = await _create_node(client)
    node_id = node["id"]

    response = await client.delete(f"/api/v1/nodes/{node_id}")
    assert response.status_code == 204

    response = await client.get(f"/api/v1/nodes/{node_id}")
    assert response.status_code == 404


async def test_delete_node_not_found(client: AsyncClient):
    """Test delete node endpoint when not found."""
    response = await client.delete(f"/api/v1/nodes/{uuid.uuid4()}")
    assert response.status_code == 404
