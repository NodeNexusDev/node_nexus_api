"""Integration tests for Script API with in-memory SQLite."""

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

from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
from app.adapters.persistence.script_gateway import (
    ScopedScriptExecutionWriter,
    SqlAlchemyScriptGateway,
)
from app.adapters.security import AesGcmCredentialCipher
from app.api.error_mapping import domain_error_handler
from app.api.v1.health import router as health_router
from app.api.v1.scripts import router as scripts_router
from app.core.exceptions import DomainError
from app.models.base import Base
from app.repositories.api_key_repo import APIKeyRepository
from app.services.api_key_service import APIKeyService
from app.services.script_execution_service import ScriptExecutionService
from app.services.script_history_service import ScriptHistoryService
from app.services.script_management_service import ScriptManagementService

MASTER_KEY = "test-master-key"

SCRIPTS_URL = "/api/v1/scripts/"


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

    @provide(scope=Scope.APP)
    def get_script_gateway(self) -> SqlAlchemyScriptGateway:
        return SqlAlchemyScriptGateway(self._sm)

    @provide(scope=Scope.REQUEST)
    def get_api_key_repo(self, session: AsyncSession) -> APIKeyRepository:
        return APIKeyRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_management_service(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptManagementService:
        return ScriptManagementService(reader=gateway, writer=gateway)

    @provide(scope=Scope.REQUEST)
    def get_history_service(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptHistoryService:
        return ScriptHistoryService(
            script_reader=gateway,
            execution_reader=gateway,
        )

    @provide(scope=Scope.REQUEST)
    def get_execution_service(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptExecutionService:
        return ScriptExecutionService(
            script_reader=gateway,
            command_reader=ScopedCommandTemplateReader(self._sm),
            node_reader=ScopedNodeConnectionReader(self._sm),
            execution_writer=ScopedScriptExecutionWriter(self._sm),
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=MagicMock(),
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
    app.include_router(scripts_router, prefix="/api/v1")
    setup_dishka(container, app)

    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": MASTER_KEY},
        ) as ac:
            yield ac

    await container.close()


async def _create_script(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    steps = [
        {
            "label": "Check disk",
            "type": "inline",
            "command": "df -h",
            "on_failure": "stop",
        }
    ]
    data: dict[str, Any] = {
        "name": "deploy_check",
        "description": "Pre-deploy check",
        "steps": steps,
        **overrides,
    }
    resp = await client.post(SCRIPTS_URL, json=data)
    assert resp.status_code == 201
    return dict(resp.json())


# --- GET /scripts/ ---


async def test_get_scripts_empty(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(SCRIPTS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_get_scripts_with_data(integration_client: AsyncClient) -> None:
    await _create_script(integration_client, name="s1")
    await _create_script(integration_client, name="s2")

    resp = await integration_client.get(SCRIPTS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 2
    names = {s["name"] for s in data["items"]}
    assert names == {"s1", "s2"}


async def test_get_scripts_pagination(integration_client: AsyncClient) -> None:
    for i in range(5):
        await _create_script(integration_client, name=f"script-{i}")

    resp = await integration_client.get(f"{SCRIPTS_URL}?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


async def test_get_scripts_pagination_invalid_params(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.get(f"{SCRIPTS_URL}?page=0")
    assert resp.status_code == 422

    resp = await integration_client.get(f"{SCRIPTS_URL}?size=0")
    assert resp.status_code == 422


# --- GET /scripts/{id} ---


async def test_get_script_found(integration_client: AsyncClient) -> None:
    script = await _create_script(integration_client)
    resp = await integration_client.get(f"/api/v1/scripts/{script['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "deploy_check"
    assert len(resp.json()["steps"]) == 1


async def test_get_script_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(f"/api/v1/scripts/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- POST /scripts/ ---


async def test_create_script(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(
        SCRIPTS_URL,
        json={
            "name": "new_script",
            "steps": [{"label": "Step 1", "type": "inline", "command": "echo ok"}],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new_script"
    assert len(data["steps"]) == 1
    assert "id" in data


async def test_create_script_multiple_steps(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.post(
        SCRIPTS_URL,
        json={
            "name": "multi_step",
            "steps": [
                {"label": "Step 1", "type": "inline", "command": "echo 1"},
                {
                    "label": "Step 2",
                    "type": "inline",
                    "command": "echo 2",
                    "on_failure": "continue",
                },
            ],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["steps"]) == 2
    assert data["steps"][1]["on_failure"] == "continue"


async def test_create_script_validation_error(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.post(SCRIPTS_URL, json={"name": "no-steps"})
    assert resp.status_code == 422


# --- PUT /scripts/{id} ---


async def test_update_script_found(integration_client: AsyncClient) -> None:
    script = await _create_script(integration_client)
    resp = await integration_client.put(
        f"/api/v1/scripts/{script['id']}",
        json={"name": "updated_script"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "updated_script"
    assert resp.json()["id"] == script["id"]


async def test_update_script_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.put(
        f"/api/v1/scripts/{uuid.uuid4()}",
        json={"name": "x"},
    )
    assert resp.status_code == 404


# --- DELETE /scripts/{id} ---


async def test_delete_script_found(integration_client: AsyncClient) -> None:
    script = await _create_script(integration_client)
    resp = await integration_client.delete(f"/api/v1/scripts/{script['id']}")
    assert resp.status_code == 204

    resp = await integration_client.get(f"/api/v1/scripts/{script['id']}")
    assert resp.status_code == 404


async def test_delete_script_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.delete(f"/api/v1/scripts/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- POST /scripts/{id}/execute ---


async def test_execute_script_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.post(
        f"/api/v1/scripts/{uuid.uuid4()}/execute",
        json={"node_ids": [str(uuid.uuid4())], "params": {}},
    )
    assert resp.status_code == 404


async def test_execute_script_node_not_found(
    integration_client: AsyncClient,
) -> None:
    script = await _create_script(integration_client)
    resp = await integration_client.post(
        f"/api/v1/scripts/{script['id']}/execute",
        json={"node_ids": [str(uuid.uuid4())], "params": {}},
    )
    # All targets are validated before any remote side effect.
    assert resp.status_code == 404
    assert resp.json()["detail"].endswith("not found")


async def test_execute_script_validation_error(
    integration_client: AsyncClient,
) -> None:
    script = await _create_script(integration_client)
    resp = await integration_client.post(
        f"/api/v1/scripts/{script['id']}/execute",
        json={},
    )
    assert resp.status_code == 422


# --- GET /scripts/{id}/executions ---


async def test_get_executions_empty(integration_client: AsyncClient) -> None:
    script = await _create_script(integration_client)
    resp = await integration_client.get(f"/api/v1/scripts/{script['id']}/executions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_get_executions_not_found(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(f"/api/v1/scripts/{uuid.uuid4()}/executions")
    assert resp.status_code == 404
