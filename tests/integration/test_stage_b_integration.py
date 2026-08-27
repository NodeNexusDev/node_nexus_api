"""Integration tests for Stage B features: Dashboard, Audit filters, Script tags."""

import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
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
from app.adapters.persistence.audit import SqlAlchemyAuditLogGateway
from app.adapters.persistence.command_history import SqlAlchemyCommandHistoryGateway
from app.adapters.persistence.command_management import SqlAlchemyCommandGateway
from app.adapters.persistence.dashboard import SqlAlchemyDashboardGateway
from app.adapters.persistence.node_management import SqlAlchemyNodeManagementGateway
from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
from app.adapters.persistence.script_gateway import (
    ScopedScriptExecutionWriter,
    SqlAlchemyScriptGateway,
)
from app.adapters.security import AesGcmCredentialCipher, HmacSha256APIKeyHasher
from app.api.error_mapping import domain_error_handler
from app.api.v1.audit import router as audit_router
from app.api.v1.commands import router as commands_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.api.v1.scripts import router as scripts_router
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import APIKeyAuthenticationService
from app.application.services.audit_log_service import AuditLogService
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.command_management_service import CommandManagementService
from app.application.services.dashboard_service import DashboardService
from app.application.services.node_command_service import NodeCommandService
from app.application.services.node_management_service import NodeManagementService
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.script_management_service import ScriptManagementService
from app.core.exceptions import DomainError
from app.models.audit_log import AuditLogModel
from app.models.base import Base

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
    def get_api_key_gateway(self) -> SqlAlchemyAPIKeyGateway:
        return SqlAlchemyAPIKeyGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_jwt_handler(self) -> JWTHandler:
        return MagicMock(spec=JWTHandler)

    @provide(scope=Scope.APP)
    def get_node_management_gateway(self) -> SqlAlchemyNodeManagementGateway:
        return SqlAlchemyNodeManagementGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_script_gateway(self) -> SqlAlchemyScriptGateway:
        return SqlAlchemyScriptGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_command_gateway(self) -> SqlAlchemyCommandGateway:
        return SqlAlchemyCommandGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_command_history_gateway(self) -> SqlAlchemyCommandHistoryGateway:
        return SqlAlchemyCommandHistoryGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_audit_log_gateway(self) -> SqlAlchemyAuditLogGateway:
        return SqlAlchemyAuditLogGateway(self._sm)

    @provide(scope=Scope.APP)
    def get_dashboard_gateway(self) -> SqlAlchemyDashboardGateway:
        return SqlAlchemyDashboardGateway(self._sm)

    @provide(scope=Scope.REQUEST)
    def get_node_management_service(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeManagementService:
        return NodeManagementService(
            reader=gateway,
            writer=gateway,
            credential_cipher=AesGcmCredentialCipher(),
        )

    @provide(scope=Scope.REQUEST)
    def get_node_command_service(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeCommandService:
        return NodeCommandService(
            node_reader=ScopedNodeConnectionReader(self._sm),
            status_writer=gateway,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=MagicMock(),
            history_writer=SqlAlchemyCommandHistoryGateway(self._sm),
        )

    @provide(scope=Scope.REQUEST)
    def get_script_management_service(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptManagementService:
        return ScriptManagementService(reader=gateway, writer=gateway)

    @provide(scope=Scope.REQUEST)
    def get_script_execution_service(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptExecutionService:
        return ScriptExecutionService(
            script_reader=gateway,
            command_reader=MagicMock(),
            node_reader=ScopedNodeConnectionReader(self._sm),
            execution_writer=ScopedScriptExecutionWriter(self._sm),
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=MagicMock(),
        )

    @provide(scope=Scope.REQUEST)
    def get_command_management_service(
        self, gateway: SqlAlchemyCommandGateway
    ) -> CommandManagementService:
        return CommandManagementService(reader=gateway, writer=gateway)

    @provide(scope=Scope.REQUEST)
    def get_command_execution_service(self) -> CommandExecutionService:
        return CommandExecutionService(
            connector_factory=MagicMock(),
            command_reader=MagicMock(),
            node_reader=ScopedNodeConnectionReader(self._sm),
            credential_cipher=AesGcmCredentialCipher(),
            history_writer=SqlAlchemyCommandHistoryGateway(self._sm),
        )

    @provide(scope=Scope.REQUEST)
    def get_audit_log_service(
        self, gateway: SqlAlchemyAuditLogGateway
    ) -> AuditLogService:
        return AuditLogService(reader=gateway, writer=gateway)

    @provide(scope=Scope.APP)
    def get_dashboard_service(
        self, gateway: SqlAlchemyDashboardGateway
    ) -> DashboardService:
        return DashboardService(reader=gateway)

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
    app.include_router(nodes_router, prefix="/api/v1")
    app.include_router(scripts_router, prefix="/api/v1")
    app.include_router(commands_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
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
    client: AsyncClient, session: AsyncSession, **overrides: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": f"node-{uuid.uuid4().hex[:8]}",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
    }
    # Remove status from overrides since API doesn't accept it
    overrides.pop("status", None)
    data.update(overrides)
    resp = await client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


async def _create_script(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": f"script-{uuid.uuid4().hex[:8]}",
        "description": "Test script",
        "steps": [
            {
                "label": "check",
                "type": "inline",
                "command": "echo ok",
                "on_failure": "stop",
            }
        ],
        **overrides,
    }
    resp = await client.post("/api/v1/scripts/", json=data)
    assert resp.status_code == 201
    return resp.json()


async def _create_command(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": f"cmd-{uuid.uuid4().hex[:8]}",
        "command": "echo hello",
        **overrides,
    }
    resp = await client.post("/api/v1/commands/", json=data)
    assert resp.status_code == 201
    return resp.json()


async def _insert_audit_log(
    session: AsyncSession,
    action: str = "create",
    node_id: uuid.UUID | None = None,
    user: str | None = None,
    created_at: datetime | None = None,
) -> AuditLogModel:
    log = AuditLogModel(
        id=uuid.uuid4(),
        node_id=node_id,
        action=action,
        user=user,
        details=None,
        created_at=created_at or datetime.now(UTC),
    )
    session.add(log)
    await session.commit()
    return log


# =============================================================================
# Dashboard tests
# =============================================================================


class TestDashboard:
    async def test_dashboard_empty(self, integration_client: AsyncClient) -> None:
        resp = await integration_client.get("/api/v1/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"]["total"] == 0
        assert data["scripts"]["total"] == 0
        assert data["commands"]["total"] == 0
        assert data["recent_activity"] == []

    async def test_dashboard_counts_nodes(
        self,
        integration_client: AsyncClient,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with sessionmaker() as session:
            await _create_node(integration_client, session, name="n1")
            await _create_node(integration_client, session, name="n2")

        resp = await integration_client.get("/api/v1/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"]["total"] == 2
        assert data["nodes"]["active"] == 2

    async def test_dashboard_counts_scripts_and_commands(
        self, integration_client: AsyncClient
    ) -> None:
        await _create_script(integration_client, name="s1")
        await _create_script(integration_client, name="s2")
        await _create_command(integration_client, name="c1")

        resp = await integration_client.get("/api/v1/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scripts"]["total"] == 2
        assert data["commands"]["total"] == 1

    async def test_dashboard_recent_activity(
        self,
        integration_client: AsyncClient,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with sessionmaker() as session:
            await _insert_audit_log(session, action="create", user="alice")
            await _insert_audit_log(session, action="update", user="bob")

        resp = await integration_client.get("/api/v1/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recent_activity"]) == 2
        actions = {entry["action"] for entry in data["recent_activity"]}
        assert actions == {"create", "update"}


# =============================================================================
# Audit filter tests
# =============================================================================


class TestAuditFilters:
    async def test_filter_by_user(
        self,
        integration_client: AsyncClient,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with sessionmaker() as session:
            await _insert_audit_log(session, action="create", user="alice")
            await _insert_audit_log(session, action="update", user="bob")
            await _insert_audit_log(session, action="delete", user="alice")

        resp = await integration_client.get("/api/v1/audit/?user=alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(item["user"] == "alice" for item in data["items"])

    async def test_filter_by_date_range(
        self,
        integration_client: AsyncClient,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        now = datetime.now(UTC)
        async with sessionmaker() as session:
            await _insert_audit_log(
                session, action="create", created_at=now - timedelta(days=10)
            )
            await _insert_audit_log(
                session, action="update", created_at=now - timedelta(days=2)
            )
            await _insert_audit_log(session, action="delete", created_at=now)

        from_date = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        to_date = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        resp = await integration_client.get(
            f"/api/v1/audit/?date_from={from_date}&date_to={to_date}"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 2
        actions = {item["action"] for item in data["items"]}
        assert actions == {"update", "delete"}

    async def test_filter_by_user_and_date(
        self,
        integration_client: AsyncClient,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        now = datetime.now(UTC)
        async with sessionmaker() as session:
            await _insert_audit_log(
                session, action="create", user="alice", created_at=now
            )
            await _insert_audit_log(
                session, action="update", user="bob", created_at=now
            )
            await _insert_audit_log(
                session,
                action="delete",
                user="alice",
                created_at=now - timedelta(days=10),
            )

        from_date = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        resp = await integration_client.get(
            f"/api/v1/audit/?user=alice&date_from={from_date}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["action"] == "create"

    async def test_filter_no_results(
        self,
        integration_client: AsyncClient,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with sessionmaker() as session:
            await _insert_audit_log(session, action="create", user="alice")

        resp = await integration_client.get("/api/v1/audit/?user=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


# =============================================================================
# Script execution with node_tags tests
# =============================================================================


class TestScriptExecuteWithTags:
    async def test_execute_requires_at_least_one_target(
        self, integration_client: AsyncClient
    ) -> None:
        script = await _create_script(integration_client)
        resp = await integration_client.post(
            f"/api/v1/scripts/{script['id']}/execute",
            json={"params": {}},
        )
        assert resp.status_code == 422

    async def test_execute_with_node_ids(self, integration_client: AsyncClient) -> None:
        script = await _create_script(integration_client)
        resp = await integration_client.post(
            f"/api/v1/scripts/{script['id']}/execute",
            json={"node_ids": [str(uuid.uuid4())], "params": {}},
        )
        # Node not found → 404
        assert resp.status_code == 404

    @pytest.mark.skip(reason="Requires PostgreSQL (@> operator for JSON arrays)")
    async def test_execute_with_node_tags_empty_result(
        self, integration_client: AsyncClient
    ) -> None:
        script = await _create_script(integration_client)
        resp = await integration_client.post(
            f"/api/v1/scripts/{script['id']}/execute",
            json={"node_tags": ["nonexistent"], "params": {}},
        )
        # Tags that match no nodes → empty results (200 with empty list)
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []

    @pytest.mark.skip(reason="Requires PostgreSQL (@> operator for JSON arrays)")
    async def test_execute_with_node_ids_and_tags(
        self, integration_client: AsyncClient
    ) -> None:
        script = await _create_script(integration_client)
        resp = await integration_client.post(
            f"/api/v1/scripts/{script['id']}/execute",
            json={
                "node_ids": [str(uuid.uuid4())],
                "node_tags": ["nonexistent"],
                "params": {},
            },
        )
        # Intersection of non-existent IDs and non-existent tags → 404
        assert resp.status_code == 404
