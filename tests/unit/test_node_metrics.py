"""Unit tests for node metrics endpoint."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.adapters.security import AesGcmCredentialCipher
from app.api.error_mapping import domain_error_handler
from app.api.v1.nodes import router as nodes_router
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.core.exceptions import ConnectionFailedError, DomainError, NodeNotFoundError
from app.schemas.node import (
    CpuMetrics,
    DiskMetrics,
    MemoryMetrics,
    NodeMetrics,
    NodeResponse,
)
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _make_node_response(**overrides: Any) -> NodeResponse:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "docker_host": None,
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeResponse(**defaults)


def _make_node_metrics(**overrides: Any) -> NodeMetrics:
    defaults: dict[str, Any] = {
        "cpu": CpuMetrics(usage_percent=25.0, cores=4),
        "memory": MemoryMetrics(
            total_bytes=8589934592,
            used_bytes=4294967296,
            percent=50.0,
        ),
        "disk": DiskMetrics(
            total_bytes=107374182400,
            used_bytes=53687091200,
            percent=50.0,
        ),
        "uptime_since": "2026-01-15 10:30:00",
    }
    defaults.update(overrides)
    return NodeMetrics(**defaults)


def _create_test_app(service: NodeManagementService | AsyncMock) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(nodes_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> NodeManagementService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_metrics_service(self) -> NodeMetricsService:
            return service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
async def client(mock_service: AsyncMock) -> AsyncClient:
    app = _create_test_app(mock_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


# --- GET /nodes/{node_id}/metrics tests ---


class TestGetNodeMetrics:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        node_id = uuid.uuid4()
        metrics = _make_node_metrics()
        mock_service.get_node_metrics.return_value = metrics

        resp = await client.get(f"/api/v1/nodes/{node_id}/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu" in data
        assert "memory" in data
        assert "disk" in data
        assert "uptime_since" in data

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        mock_service.get_node_metrics.side_effect = NodeNotFoundError("not found")

        resp = await client.get(f"/api/v1/nodes/{node_id}/metrics")
        assert resp.status_code == 404

    async def test_connection_failed(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        mock_service.get_node_metrics.side_effect = ConnectionFailedError(
            "SSH connection failed"
        )

        resp = await client.get(f"/api/v1/nodes/{node_id}/metrics")
        assert resp.status_code == 503

    async def test_cpu_metrics_structure(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        metrics = _make_node_metrics(cpu=CpuMetrics(usage_percent=75.5, cores=8))
        mock_service.get_node_metrics.return_value = metrics

        resp = await client.get(f"/api/v1/nodes/{node_id}/metrics")
        data = resp.json()
        assert data["cpu"]["usage_percent"] == 75.5
        assert data["cpu"]["cores"] == 8

    async def test_memory_metrics_structure(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        metrics = _make_node_metrics(
            memory=MemoryMetrics(
                total_bytes=17179869184,
                used_bytes=8589934592,
                percent=50.0,
            )
        )
        mock_service.get_node_metrics.return_value = metrics

        resp = await client.get(f"/api/v1/nodes/{node_id}/metrics")
        data = resp.json()
        assert data["memory"]["total_bytes"] == 17179869184
        assert data["memory"]["used_bytes"] == 8589934592
        assert data["memory"]["percent"] == 50.0

    async def test_disk_metrics_structure(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        metrics = _make_node_metrics(
            disk=DiskMetrics(
                total_bytes=214748364800,
                used_bytes=107374182400,
                percent=50.0,
            )
        )
        mock_service.get_node_metrics.return_value = metrics

        resp = await client.get(f"/api/v1/nodes/{node_id}/metrics")
        data = resp.json()
        assert data["disk"]["total_bytes"] == 214748364800
        assert data["disk"]["used_bytes"] == 107374182400
        assert data["disk"]["percent"] == 50.0


# --- NodeMetrics schema tests ---


class TestNodeMetricsSchema:
    def test_valid_metrics(self) -> None:
        metrics = _make_node_metrics()
        assert metrics.cpu.usage_percent == 25.0
        assert metrics.cpu.cores == 4
        assert metrics.memory.total_bytes == 8589934592
        assert metrics.disk.percent == 50.0
        assert metrics.uptime_since == "2026-01-15 10:30:00"

    def test_cpu_metrics_validation(self) -> None:
        # Valid
        cpu = CpuMetrics(usage_percent=50.0, cores=4)
        assert cpu.usage_percent == 50.0

        # Invalid - negative usage
        with pytest.raises(Exception):
            CpuMetrics(usage_percent=-1, cores=4)

        # Invalid - usage > 100
        with pytest.raises(Exception):
            CpuMetrics(usage_percent=101, cores=4)

    def test_memory_metrics_validation(self) -> None:
        mem = MemoryMetrics(total_bytes=1000, used_bytes=500, percent=50.0)
        assert mem.total_bytes == 1000

    def test_disk_metrics_validation(self) -> None:
        disk = DiskMetrics(total_bytes=1000, used_bytes=500, percent=50.0)
        assert disk.total_bytes == 1000


# --- NodeMetricsService tests ---


class MockAsyncContextManager:
    """Mock async context manager for connector."""

    def __init__(self, connector):
        self._connector = connector

    async def __aenter__(self):
        return self._connector

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def __getattr__(self, name):
        return getattr(self._connector, name)


class TestNodeMetricsService:
    @pytest.mark.asyncio
    async def test_reads_node_before_opening_remote_session(self) -> None:
        order: list[str] = []
        reader = AsyncMock()
        factory = MagicMock()
        node = MagicMock(
            id=uuid.uuid4(),
            host="10.0.0.1",
            port=22,
            username="root",
            password=None,
            ssh_key=None,
            passphrase=None,
        )

        async def read_node(_node_id):  # noqa: ANN001
            order.append("read")
            return node

        connector = AsyncMock()

        async def enter_connector():
            order.append("remote")
            return connector

        async def execute(command: str) -> tuple[str, str, int]:
            if "top" in command:
                return ("1.0", "", 0)
            if "nproc" in command:
                return ("1", "", 0)
            if "free" in command or "df" in command:
                return ("100 50 50", "", 0)
            return ("2026-07-29 10:00:00", "", 0)

        reader.get_connection.side_effect = read_node
        connector.__aenter__.side_effect = enter_connector
        connector.__aexit__.return_value = None
        connector.execute_command.side_effect = execute
        factory.create_ssh.return_value = connector
        service = NodeMetricsService(
            node_reader=reader,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=factory,
        )

        await service.collect(node.id)

        assert order == ["read", "remote"]

    @pytest.mark.asyncio
    async def test_get_node_metrics_success(self) -> None:
        """get_node_metrics returns metrics from SSH."""
        mock_repo = AsyncMock()
        mock_factory = MagicMock()

        # Mock node
        mock_node = MagicMock()
        mock_node.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_node.host = "10.0.0.1"
        mock_node.port = 22
        mock_node.username = "root"
        mock_node.password = None
        mock_node.ssh_key = None
        mock_node.passphrase = None

        mock_repo.get_connection.return_value = mock_node

        # Mock connector
        mock_connector = AsyncMock()

        # Mock SSH commands
        async def mock_execute(cmd):
            if "top" in cmd:
                return ("25.0", "", 0)
            elif "nproc" in cmd:
                return ("4", "", 0)
            elif "free" in cmd:
                return ("8589934592 4294967296 4294967296", "", 0)
            elif "df" in cmd:
                return ("107374182400 53687091200 53687091200", "", 0)
            elif "uptime" in cmd:
                return ("2026-01-15 10:30:00", "", 0)
            return ("", "", 0)

        mock_connector.execute_command = mock_execute
        mock_factory.create_ssh.return_value = MockAsyncContextManager(mock_connector)

        service = NodeMetricsService(
            node_reader=mock_repo,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=mock_factory,
        )
        metrics = await service.collect(
            uuid.UUID("00000000-0000-0000-0000-000000000001")
        )

        assert metrics.cpu.usage_percent == 25.0
        assert metrics.cpu.cores == 4
        assert metrics.memory.total_bytes == 8589934592
        assert metrics.memory.used_bytes == 4294967296
        assert metrics.disk.total_bytes == 107374182400
        assert metrics.disk.used_bytes == 53687091200
        assert metrics.uptime_since == "2026-01-15 10:30:00"

    @pytest.mark.asyncio
    async def test_get_node_metrics_connection_error(self) -> None:
        """get_node_metrics raises ConnectionFailedError on SSH error."""
        from app.core.exceptions import ConnectionFailedError

        mock_repo = AsyncMock()
        mock_factory = MagicMock()

        mock_node = MagicMock()
        mock_node.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_node.host = "10.0.0.1"
        mock_node.port = 22
        mock_node.username = "root"
        mock_node.password = None
        mock_node.ssh_key = None
        mock_node.passphrase = None

        mock_repo.get_connection.return_value = mock_node

        mock_connector = AsyncMock()
        mock_connector.execute_command.side_effect = Exception("Connection failed")
        mock_factory.create_ssh.return_value = MockAsyncContextManager(mock_connector)

        service = NodeMetricsService(
            node_reader=mock_repo,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=mock_factory,
        )

        with pytest.raises(ConnectionFailedError):
            await service.collect(uuid.UUID("00000000-0000-0000-0000-000000000001"))
