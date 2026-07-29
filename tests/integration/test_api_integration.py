"""Integration tests for API endpoints with in-memory SQLite."""

import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.error_mapping import domain_error_handler
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.core.exceptions import DomainError
from app.models.base import Base
from app.repositories.api_key_repo import APIKeyRepository
from app.repositories.node_repo import NodeRepository
from app.services.api_key_service import APIKeyService
from app.services.node_bulk_command_service import NodeBulkCommandService
from app.services.node_command_service import NodeCommandService
from app.services.node_metrics_service import NodeMetricsService
from app.services.node_service import NodeService

MASTER_KEY = "test-master-key"

NODES_URL = "/api/v1/nodes/"


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class IntegrationDbProvider(Provider):
    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self._sm = sm

    @provide(scope=Scope.REQUEST)
    async def get_session(self) -> AsyncIterable[AsyncSession]:
        async with self._sm() as session:
            async with session.begin():
                yield session

    @provide(scope=Scope.REQUEST)
    def get_repo(self, session: AsyncSession) -> NodeRepository:
        return NodeRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_api_key_repo(self, session: AsyncSession) -> APIKeyRepository:
        return APIKeyRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_node_command_service(self, repo: NodeRepository) -> NodeCommandService:
        return NodeCommandService(repository=repo)

    @provide(scope=Scope.REQUEST)
    def get_node_bulk_command_service(
        self,
        repo: NodeRepository,
    ) -> NodeBulkCommandService:
        return NodeBulkCommandService(repository=repo)

    @provide(scope=Scope.REQUEST)
    def get_node_metrics_service(self, repo: NodeRepository) -> NodeMetricsService:
        return NodeMetricsService(repository=repo)

    @provide(scope=Scope.REQUEST)
    def get_service(
        self,
        repo: NodeRepository,
        command_service: NodeCommandService,
        bulk_command_service: NodeBulkCommandService,
    ) -> NodeService:
        return NodeService(
            repository=repo,
            command_service=command_service,
            bulk_command_service=bulk_command_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(self, repo: APIKeyRepository) -> APIKeyService:
        return APIKeyService(repository=repo)


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


@pytest_asyncio.fixture
async def integration_client(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    provider = IntegrationDbProvider(sessionmaker)
    container = make_async_container(provider)

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    setup_dishka(container, app)

    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": MASTER_KEY},
        ) as ac:
            yield ac

    await container.close()


async def _create_node(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        **overrides,
    }
    resp = await client.post(NODES_URL, json=data)
    assert resp.status_code == 201
    return dict(resp.json())


# --- GET /nodes/ ---


async def test_get_nodes_empty(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(NODES_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_get_nodes_with_data(integration_client: AsyncClient) -> None:
    await _create_node(integration_client, name="n1")
    await _create_node(integration_client, name="n2")

    resp = await integration_client.get(NODES_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 2
    names = {n["name"] for n in data["items"]}
    assert names == {"n1", "n2"}


async def test_get_nodes_pagination(integration_client: AsyncClient) -> None:
    for i in range(5):
        await _create_node(integration_client, name=f"node-{i}")

    resp = await integration_client.get(f"{NODES_URL}?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 2


async def test_get_nodes_pagination_page_2(integration_client: AsyncClient) -> None:
    for i in range(5):
        await _create_node(integration_client, name=f"node-{i}")

    resp = await integration_client.get(f"{NODES_URL}?page=2&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["page"] == 2
    names = {n["name"] for n in data["items"]}
    assert names == {"node-2", "node-3"}


async def test_get_nodes_pagination_empty_page(integration_client: AsyncClient) -> None:
    for i in range(3):
        await _create_node(integration_client, name=f"node-{i}")

    resp = await integration_client.get(f"{NODES_URL}?page=10&size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 3


async def test_get_nodes_pagination_invalid_params(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.get(f"{NODES_URL}?page=0")
    assert resp.status_code == 422

    resp = await integration_client.get(f"{NODES_URL}?size=0")
    assert resp.status_code == 422

    resp = await integration_client.get(f"{NODES_URL}?size=200")
    assert resp.status_code == 422


async def test_get_nodes_pagination_response_structure(
    integration_client: AsyncClient,
) -> None:
    await _create_node(integration_client)

    resp = await integration_client.get(NODES_URL)
    assert resp.status_code == 200
    data = resp.json()

    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert isinstance(data["page"], int)
    assert isinstance(data["size"], int)


# --- GET /nodes/{id} ---


async def test_get_node_found(integration_client: AsyncClient) -> None:
    node = await _create_node(integration_client)
    resp = await integration_client.get(f"/api/v1/nodes/{node['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "test-node"


async def test_get_node_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(f"/api/v1/nodes/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- POST /nodes/ ---


async def test_create_node(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(
        NODES_URL,
        json={
            "name": "new-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new-node"
    assert data["host"] == "10.0.0.1"
    assert "id" in data
    assert data["status"] == "active"


async def test_create_node_validation_error(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.post(
        NODES_URL,
        json={"name": "incomplete"},
    )
    assert resp.status_code == 422


# --- PUT /nodes/{id} ---


async def test_update_node_found(integration_client: AsyncClient) -> None:
    node = await _create_node(integration_client)
    resp = await integration_client.put(
        f"/api/v1/nodes/{node['id']}",
        json={"name": "updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "updated"
    assert resp.json()["id"] == node["id"]


async def test_update_node_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.put(
        f"/api/v1/nodes/{uuid.uuid4()}",
        json={"name": "x"},
    )
    assert resp.status_code == 404


# --- DELETE /nodes/{id} ---


async def test_delete_node_found(integration_client: AsyncClient) -> None:
    node = await _create_node(integration_client)
    resp = await integration_client.delete(f"/api/v1/nodes/{node['id']}")
    assert resp.status_code == 204

    resp = await integration_client.get(f"/api/v1/nodes/{node['id']}")
    assert resp.status_code == 404


async def test_delete_node_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.delete(f"/api/v1/nodes/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- POST /nodes/{id}/check ---


async def test_check_node_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(f"/api/v1/nodes/{uuid.uuid4()}/check")
    assert resp.status_code == 404


# --- POST /nodes/{id}/execute ---


async def test_execute_command_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(
        f"/api/v1/nodes/{uuid.uuid4()}/execute",
        json={"command": "ls"},
    )
    assert resp.status_code == 404


async def test_execute_command_validation_error(
    integration_client: AsyncClient,
) -> None:
    node = await _create_node(integration_client)
    resp = await integration_client.post(
        f"/api/v1/nodes/{node['id']}/execute",
        json={},
    )
    assert resp.status_code == 422


# --- Health ---


async def test_health_check(integration_client: AsyncClient) -> None:
    resp = await integration_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data
