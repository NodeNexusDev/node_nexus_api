"""Integration tests for node command history and bulk history with in-memory SQLite."""

import uuid
from collections.abc import AsyncGenerator, AsyncIterable
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

from app.adapters.persistence.api_key import SqlAlchemyAPIKeyGateway
from app.adapters.persistence.command_history import SqlAlchemyCommandHistoryGateway
from app.adapters.persistence.dao.command_execution import CommandExecutionRepository
from app.adapters.persistence.node_management import SqlAlchemyNodeManagementGateway
from app.adapters.security import HmacSha256APIKeyHasher
from app.api.error_mapping import domain_error_handler
from app.api.v1.commands import router as commands_router
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import APIKeyAuthenticationService
from app.application.services.execution_history_service import ExecutionHistoryService
from app.application.services.node_management_service import NodeManagementService
from app.core.exceptions import DomainError
from app.models.base import Base
from app.models.command import CommandModel  # noqa: F401 — registers with Base
from app.models.command_execution import CommandExecutionModel  # noqa: F401
from app.models.node import NodeModel  # noqa: F401
from tests.types import UnvalidatedJsonObject
from tests.typing import as_typed_mock

MASTER_KEY = "test-master-key"


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
    def get_node_management_gateway(self) -> SqlAlchemyNodeManagementGateway:
        return SqlAlchemyNodeManagementGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_command_history_gateway(self) -> SqlAlchemyCommandHistoryGateway:
        return SqlAlchemyCommandHistoryGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_api_key_gateway(self) -> SqlAlchemyAPIKeyGateway:
        return SqlAlchemyAPIKeyGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_jwt_handler(self) -> JWTHandler:
        return as_typed_mock(JWTHandler, MagicMock(spec=JWTHandler))

    @provide(scope=Scope.REQUEST)
    def get_node_management_service(
        self,
        gateway: SqlAlchemyNodeManagementGateway,
    ) -> NodeManagementService:
        return NodeManagementService(
            reader=gateway,
            writer=gateway,
            credential_cipher=MagicMock(),
        )

    @provide(scope=Scope.APP)
    def get_execution_history_service(
        self,
        gateway: SqlAlchemyCommandHistoryGateway,
    ) -> ExecutionHistoryService:
        return ExecutionHistoryService(gateway)

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(
        self, gateway: SqlAlchemyAPIKeyGateway
    ) -> APIKeyAuthenticationService:
        return APIKeyAuthenticationService(gateway, gateway, HmacSha256APIKeyHasher())


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
    app.include_router(commands_router, prefix="/api/v1")
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


async def _create_node(
    client: AsyncClient, **overrides: object
) -> UnvalidatedJsonObject:
    data = {
        "name": "test-node",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        **overrides,
    }
    resp = await client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# GET /nodes/{id}/commands/history
# ---------------------------------------------------------------------------


async def test_node_history_empty(integration_client: AsyncClient) -> None:
    node = await _create_node(integration_client, name="hist-empty")
    resp = await integration_client.get(
        "/api/v1/commands/history",
        params={"node_id": node["id"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_node_history_returns_records(
    integration_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    node = await _create_node(integration_client, name="hist-records")
    node_id = uuid.UUID(node["id"])

    # Insert history records directly via repository
    async with sessionmaker() as session:
        repo = CommandExecutionRepository(session)
        await repo.create(
            {
                "node_id": node_id,
                "command_fingerprint": "fp-aaa",
                "exit_code": 0,
                "stdout": "ok",
                "stderr": "",
                "stdout_bytes": 2,
                "stderr_bytes": 0,
                "truncated": False,
            }
        )
        await repo.create(
            {
                "node_id": node_id,
                "command_fingerprint": "fp-bbb",
                "exit_code": 1,
                "stdout": "",
                "stderr": "fail",
                "stdout_bytes": 0,
                "stderr_bytes": 4,
                "truncated": False,
            }
        )
        await session.commit()

    resp = await integration_client.get(
        "/api/v1/commands/history",
        params={"node_id": node["id"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    fingerprints = {item["command_fingerprint"] for item in data["items"]}
    assert "fp-aaa" in fingerprints
    assert "fp-bbb" in fingerprints


async def test_node_history_pagination(
    integration_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    node = await _create_node(integration_client, name="hist-page")
    node_id = uuid.UUID(node["id"])

    async with sessionmaker() as session:
        repo = CommandExecutionRepository(session)
        for i in range(5):
            await repo.create(
                {
                    "node_id": node_id,
                    "command_fingerprint": f"fp-{i:03d}",
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                    "truncated": False,
                }
            )
        await session.commit()

    resp = await integration_client.get(
        "/api/v1/commands/history",
        params={"node_id": node["id"], "page": "1", "size": "2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


# ---------------------------------------------------------------------------
# GET /nodes/bulk/history
# ---------------------------------------------------------------------------


async def test_bulk_history_empty(integration_client: AsyncClient) -> None:
    resp = await integration_client.get(
        "/api/v1/commands/bulk/history",
        params={"batch_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_bulk_history_returns_records(
    integration_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    batch_id = uuid.uuid4()

    async with sessionmaker() as session:
        repo = CommandExecutionRepository(session)
        await repo.create(
            {
                "node_id": uuid.uuid4(),
                "batch_id": batch_id,
                "command_fingerprint": "bulk-fp-1",
                "exit_code": 0,
                "stdout": "ok",
                "stderr": "",
                "stdout_bytes": 2,
                "stderr_bytes": 0,
                "truncated": False,
            }
        )
        await repo.create(
            {
                "node_id": uuid.uuid4(),
                "batch_id": batch_id,
                "command_fingerprint": "bulk-fp-2",
                "exit_code": 1,
                "stdout": "",
                "stderr": "err",
                "stdout_bytes": 0,
                "stderr_bytes": 3,
                "truncated": False,
            }
        )
        await session.commit()

    resp = await integration_client.get(
        "/api/v1/commands/bulk/history",
        params={"batch_id": str(batch_id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_bulk_history_filters_by_batch_id(
    integration_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    batch_a = uuid.uuid4()
    batch_b = uuid.uuid4()

    async with sessionmaker() as session:
        repo = CommandExecutionRepository(session)
        await repo.create(
            {
                "node_id": uuid.uuid4(),
                "batch_id": batch_a,
                "command_fingerprint": "fp-a",
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "stdout_bytes": 0,
                "stderr_bytes": 0,
                "truncated": False,
            }
        )
        await repo.create(
            {
                "node_id": uuid.uuid4(),
                "batch_id": batch_b,
                "command_fingerprint": "fp-b",
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "stdout_bytes": 0,
                "stderr_bytes": 0,
                "truncated": False,
            }
        )
        await session.commit()

    resp_a = await integration_client.get(
        "/api/v1/commands/bulk/history",
        params={"batch_id": str(batch_a)},
    )
    resp_b = await integration_client.get(
        "/api/v1/commands/bulk/history",
        params={"batch_id": str(batch_b)},
    )
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert resp_a.json()["total"] == 1
    assert resp_b.json()["total"] == 1
    assert resp_a.json()["items"][0]["batch_id"] == str(batch_a)
    assert resp_b.json()["items"][0]["batch_id"] == str(batch_b)


async def test_bulk_history_pagination(
    integration_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    batch_id = uuid.uuid4()

    async with sessionmaker() as session:
        repo = CommandExecutionRepository(session)
        for i in range(3):
            await repo.create(
                {
                    "node_id": uuid.uuid4(),
                    "batch_id": batch_id,
                    "command_fingerprint": f"bulk-{i}",
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                    "truncated": False,
                }
            )
        await session.commit()

    resp = await integration_client.get(
        "/api/v1/commands/bulk/history",
        params={"batch_id": str(batch_id), "page": "1", "size": "2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2


async def test_bulk_history_missing_batch_id(integration_client: AsyncClient) -> None:
    resp = await integration_client.get("/api/v1/commands/bulk/history")
    assert resp.status_code == 422
