"""Integration tests for Command API with in-memory SQLite."""

import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.v1.commands import router as commands_router
from app.api.v1.health import router as health_router
from app.models.base import Base
from app.repositories.api_key_repo import APIKeyRepository
from app.repositories.command_repo import CommandRepository
from app.repositories.node_repo import NodeRepository
from app.services.api_key_service import APIKeyService
from app.services.command_service import CommandService

MASTER_KEY = "test-master-key"

COMMANDS_URL = "/api/v1/commands/"


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
    def get_command_repo(self, session: AsyncSession) -> CommandRepository:
        return CommandRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_node_repo(self, session: AsyncSession) -> NodeRepository:
        return NodeRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_api_key_repo(self, session: AsyncSession) -> APIKeyRepository:
        return APIKeyRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_service(
        self,
        command_repo: CommandRepository,
        node_repo: NodeRepository,
    ) -> CommandService:
        return CommandService(
            repository=command_repo,
            node_repository=node_repo,
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
    app.include_router(health_router)
    app.include_router(commands_router, prefix="/api/v1")
    setup_dishka(container, app)

    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": MASTER_KEY},
        ) as ac:
            yield ac

    await container.close()


async def _create_command(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "check_disk",
        "command": "df -h",
        "description": "Check disk usage",
        **overrides,
    }
    resp = await client.post(COMMANDS_URL, json=data)
    assert resp.status_code == 201
    return dict(resp.json())


# --- GET /commands/ ---


@pytest.mark.asyncio
async def test_get_commands_empty(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(COMMANDS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_commands_with_data(integration_client: AsyncClient) -> None:
    await _create_command(integration_client, name="c1")
    await _create_command(integration_client, name="c2")

    resp = await integration_client.get(COMMANDS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 2
    names = {c["name"] for c in data["items"]}
    assert names == {"c1", "c2"}


@pytest.mark.asyncio
async def test_get_commands_pagination(integration_client: AsyncClient) -> None:
    for i in range(5):
        await _create_command(integration_client, name=f"cmd-{i}")

    resp = await integration_client.get(f"{COMMANDS_URL}?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


@pytest.mark.asyncio
async def test_get_commands_pagination_invalid_params(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.get(f"{COMMANDS_URL}?page=0")
    assert resp.status_code == 422

    resp = await integration_client.get(f"{COMMANDS_URL}?size=0")
    assert resp.status_code == 422


# --- GET /commands/{id} ---


@pytest.mark.asyncio
async def test_get_command_found(integration_client: AsyncClient) -> None:
    cmd = await _create_command(integration_client)
    resp = await integration_client.get(f"/api/v1/commands/{cmd['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "check_disk"


@pytest.mark.asyncio
async def test_get_command_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(f"/api/v1/commands/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- POST /commands/ ---


@pytest.mark.asyncio
async def test_create_command(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(
        COMMANDS_URL,
        json={"name": "new_cmd", "command": "echo test"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new_cmd"
    assert data["command"] == "echo test"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_command_with_parameters(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(
        COMMANDS_URL,
        json={
            "name": "restart_svc",
            "command": "systemctl restart {service}",
            "parameters": [{"name": "service", "type": "string", "required": True}],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["parameters"] is not None
    assert len(data["parameters"]) == 1
    assert data["parameters"][0]["name"] == "service"


@pytest.mark.asyncio
async def test_create_command_validation_error(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.post(COMMANDS_URL, json={"name": "incomplete"})
    assert resp.status_code == 422


# --- PUT /commands/{id} ---


@pytest.mark.asyncio
async def test_update_command_found(integration_client: AsyncClient) -> None:
    cmd = await _create_command(integration_client)
    resp = await integration_client.put(
        f"/api/v1/commands/{cmd['id']}",
        json={"name": "updated_cmd"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "updated_cmd"
    assert resp.json()["id"] == cmd["id"]


@pytest.mark.asyncio
async def test_update_command_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.put(
        f"/api/v1/commands/{uuid.uuid4()}",
        json={"name": "x"},
    )
    assert resp.status_code == 404


# --- DELETE /commands/{id} ---


@pytest.mark.asyncio
async def test_delete_command_found(integration_client: AsyncClient) -> None:
    cmd = await _create_command(integration_client)
    resp = await integration_client.delete(f"/api/v1/commands/{cmd['id']}")
    assert resp.status_code == 204

    resp = await integration_client.get(f"/api/v1/commands/{cmd['id']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_command_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.delete(f"/api/v1/commands/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- POST /commands/{id}/execute ---


@pytest.mark.asyncio
async def test_execute_command_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(
        f"/api/v1/commands/{uuid.uuid4()}/execute",
        json={"node_id": str(uuid.uuid4()), "params": {}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_execute_command_node_not_found(
    integration_client: AsyncClient,
) -> None:
    cmd = await _create_command(integration_client)
    resp = await integration_client.post(
        f"/api/v1/commands/{cmd['id']}/execute",
        json={"node_id": str(uuid.uuid4()), "params": {}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_execute_command_validation_error(
    integration_client: AsyncClient,
) -> None:
    cmd = await _create_command(integration_client)
    resp = await integration_client.post(
        f"/api/v1/commands/{cmd['id']}/execute",
        json={},
    )
    assert resp.status_code == 422
