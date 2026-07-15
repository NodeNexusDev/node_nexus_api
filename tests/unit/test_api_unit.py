"""Unit tests for API endpoints with mocked services via dishka."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.schemas.node import CommandResult, NodeResponse
from app.services.node_service import NodeService
from tests.unit.conftest import MockSessionmaker, _mock_settings


def _make_node(**overrides: Any) -> NodeResponse:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeResponse(**defaults)


def _create_test_app(service: NodeService | AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    app.state.sessionmaker = MockSessionmaker()

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> NodeService:
            return service

    container = make_async_container(MockServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=NodeService)


@pytest.fixture
async def client(mock_service: AsyncMock) -> AsyncGenerator[AsyncClient]:
    app = _create_test_app(mock_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


# --- GET /nodes ---


class TestGetNodes:
    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_all_nodes.return_value = ([], 0)
        response = await client.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20

    async def test_returns_nodes(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        nodes = [_make_node(name="n1"), _make_node(name="n2")]
        mock_service.get_all_nodes.return_value = (nodes, 2)
        response = await client.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2
        assert data["items"][0]["name"] == "n1"

    async def test_pagination_params(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_all_nodes.return_value = ([], 0)
        await client.get("/api/v1/nodes?page=2&size=10")
        mock_service.get_all_nodes.assert_called_once_with(skip=10, limit=10)


# --- GET /nodes/{id} ---


class TestGetNode:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        node = _make_node()
        mock_service.get_node.return_value = node
        response = await client.get(f"/api/v1/nodes/{node.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(node.id)

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_node.side_effect = NodeNotFoundError("not found")
        response = await client.get(f"/api/v1/nodes/{uuid.uuid4()}")
        assert response.status_code == 404


# --- POST /nodes ---


class TestCreateNode:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        node = _make_node(name="new-node")
        mock_service.create_node.return_value = node
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
        assert response.json()["name"] == "new-node"

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post("/api/v1/nodes", json={"name": "only-name"})
        assert response.status_code == 422


# --- PUT /nodes/{id} ---


class TestUpdateNode:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        node = _make_node(name="updated")
        mock_service.update_node.return_value = node
        response = await client.put(
            f"/api/v1/nodes/{node.id}",
            json={"name": "updated"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated"

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.update_node.side_effect = NodeNotFoundError("not found")
        response = await client.put(
            f"/api/v1/nodes/{uuid.uuid4()}",
            json={"name": "x"},
        )
        assert response.status_code == 404


# --- DELETE /nodes/{id} ---


class TestDeleteNode:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.delete_node.return_value = True
        response = await client.delete(f"/api/v1/nodes/{uuid.uuid4()}")
        assert response.status_code == 204

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.delete_node.side_effect = NodeNotFoundError("not found")
        response = await client.delete(f"/api/v1/nodes/{uuid.uuid4()}")
        assert response.status_code == 404


# --- POST /nodes/{id}/check ---


class TestCheckNode:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        node = _make_node(status="active")
        mock_service.check_connectivity.return_value = node
        response = await client.post(f"/api/v1/nodes/{node.id}/check")
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.check_connectivity.side_effect = NodeNotFoundError("not found")
        response = await client.post(f"/api/v1/nodes/{uuid.uuid4()}/check")
        assert response.status_code == 404

    async def test_connection_failed(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.check_connectivity.side_effect = ConnectionFailedError("timeout")
        response = await client.post(f"/api/v1/nodes/{uuid.uuid4()}/check")
        assert response.status_code == 503


# --- POST /nodes/{id}/execute ---


class TestExecuteCommand:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        result = CommandResult(stdout="ok", stderr="", exit_code=0)
        mock_service.execute_command.return_value = result
        response = await client.post(
            f"/api/v1/nodes/{uuid.uuid4()}/execute",
            json={"command": "uptime"},
        )
        assert response.status_code == 200
        assert response.json()["stdout"] == "ok"
        assert response.json()["exit_code"] == 0

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_command.side_effect = NodeNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{uuid.uuid4()}/execute",
            json={"command": "ls"},
        )
        assert response.status_code == 404

    async def test_connection_failed(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_command.side_effect = ConnectionFailedError("refused")
        response = await client.post(
            f"/api/v1/nodes/{uuid.uuid4()}/execute",
            json={"command": "ls"},
        )
        assert response.status_code == 503

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post(
            f"/api/v1/nodes/{uuid.uuid4()}/execute",
            json={},
        )
        assert response.status_code == 422


# --- Health ---


class TestHealth:
    async def test_health_check(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
