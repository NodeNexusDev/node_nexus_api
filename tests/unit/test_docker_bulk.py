"""Unit tests for bulk Docker operations."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.docker_bulk import router as docker_bulk_router
from app.application.services.docker.bulk_service import DockerBulkService
from app.schemas.docker import BulkDockerNodeResult, BulkDockerResponse
from tests.docker_test_facade import DockerService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_test_app(service: DockerService | AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(docker_bulk_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> DockerBulkService:
            return service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=DockerService)


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


class TestBulkStartContainers:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.bulk_container_action.return_value = BulkDockerResponse(
            action="start",
            results=[
                BulkDockerNodeResult(
                    node_id="node-1",
                    node_name="server1",
                    status="success",
                    output="",
                )
            ],
            total=1,
            succeeded=1,
            failed=0,
        )

        resp = await client.post(
            "/api/v1/docker/bulk/start",
            json={"node_ids": ["node-1"], "container_id": "nginx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "start"
        assert data["succeeded"] == 1
        assert data["failed"] == 0

    async def test_partial_failure(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.bulk_container_action.return_value = BulkDockerResponse(
            action="start",
            results=[
                BulkDockerNodeResult(
                    node_id="node-1",
                    node_name="server1",
                    status="success",
                ),
                BulkDockerNodeResult(
                    node_id="node-2",
                    node_name="server2",
                    status="error",
                    error="Node not found",
                ),
            ],
            total=2,
            succeeded=1,
            failed=1,
        )

        resp = await client.post(
            "/api/v1/docker/bulk/start",
            json={"node_ids": ["node-1", "node-2"], "container_id": "nginx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1


class TestBulkStopContainers:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.bulk_container_action.return_value = BulkDockerResponse(
            action="stop",
            results=[
                BulkDockerNodeResult(
                    node_id="node-1",
                    node_name="server1",
                    status="success",
                )
            ],
            total=1,
            succeeded=1,
            failed=0,
        )

        resp = await client.post(
            "/api/v1/docker/bulk/stop",
            json={"node_ids": ["node-1"], "container_id": "nginx", "timeout": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "stop"
        assert data["succeeded"] == 1


class TestBulkRestartContainers:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.bulk_container_action.return_value = BulkDockerResponse(
            action="restart",
            results=[
                BulkDockerNodeResult(
                    node_id="node-1",
                    node_name="server1",
                    status="success",
                )
            ],
            total=1,
            succeeded=1,
            failed=0,
        )

        resp = await client.post(
            "/api/v1/docker/bulk/restart",
            json={"node_ids": ["node-1"], "container_id": "nginx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "restart"


class TestBulkExecInContainers:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.bulk_exec.return_value = BulkDockerResponse(
            action="exec",
            results=[
                BulkDockerNodeResult(
                    node_id="node-1",
                    node_name="server1",
                    status="success",
                    output="hello",
                )
            ],
            total=1,
            succeeded=1,
            failed=0,
        )

        resp = await client.post(
            "/api/v1/docker/bulk/exec",
            json={
                "node_ids": ["node-1"],
                "container_id": "nginx",
                "command": "echo hello",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "exec"
        assert data["results"][0]["output"] == "hello"

    async def test_missing_command(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        resp = await client.post(
            "/api/v1/docker/bulk/exec",
            json={"node_ids": ["node-1"], "container_id": "nginx"},
        )
        assert resp.status_code == 422


class TestBulkByTags:
    async def test_start_by_tags_only(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.bulk_container_action.return_value = BulkDockerResponse(
            action="start",
            results=[
                BulkDockerNodeResult(
                    node_id="node-1", node_name="server1", status="success"
                )
            ],
            total=1,
            succeeded=1,
            failed=0,
        )
        resp = await client.post(
            "/api/v1/docker/bulk/start",
            json={"node_tags": ["zone-a"], "container_id": "nginx"},
        )
        assert resp.status_code == 200
        mock_service.bulk_container_action.assert_called_once_with(
            node_ids=[],
            container_id="nginx",
            action="start",
            node_tags=["zone-a"],
        )

    async def test_mixed_ids_and_tags_passed(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.bulk_container_action.return_value = BulkDockerResponse(
            action="stop", results=[], total=0, succeeded=0, failed=0
        )
        resp = await client.post(
            "/api/v1/docker/bulk/stop",
            json={
                "node_ids": ["node-1"],
                "node_tags": ["zone-a"],
                "container_id": "nginx",
                "timeout": 5,
            },
        )
        assert resp.status_code == 200
        mock_service.bulk_container_action.assert_called_once_with(
            node_ids=["node-1"],
            container_id="nginx",
            action="stop",
            timeout=5,
            node_tags=["zone-a"],
        )

    async def test_no_targets_returns_422(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        resp = await client.post(
            "/api/v1/docker/bulk/restart",
            json={"container_id": "nginx"},
        )
        assert resp.status_code == 422

    async def test_exec_by_tags(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.bulk_exec.return_value = BulkDockerResponse(
            action="exec", results=[], total=0, succeeded=0, failed=0
        )
        resp = await client.post(
            "/api/v1/docker/bulk/exec",
            json={
                "node_tags": ["zone-a"],
                "container_id": "nginx",
                "command": "echo hi",
            },
        )
        assert resp.status_code == 200
        mock_service.bulk_exec.assert_called_once_with(
            node_ids=[],
            container_id="nginx",
            command="echo hi",
            timeout=30,
            node_tags=["zone-a"],
        )


class TestBulkDockerSchemas:
    def test_bulk_request(self) -> None:
        from app.schemas.docker import BulkDockerRequest

        req = BulkDockerRequest(
            node_ids=["node-1", "node-2"],
            container_id="abc123def456",
        )
        assert len(req.node_ids) == 2
        assert req.container_id == "abc123def456"
        assert req.timeout is None
        assert req.command is None
        assert req.node_tags == []

    def test_bulk_request_tags_only(self) -> None:
        from app.schemas.docker import BulkDockerRequest

        req = BulkDockerRequest(
            node_tags=["zone-a"],
            container_id="abc123def456",
        )
        assert req.node_ids == []
        assert req.node_tags == ["zone-a"]

    def test_bulk_request_requires_targets(self) -> None:
        from pydantic import ValidationError

        from app.schemas.docker import BulkDockerRequest

        with pytest.raises(ValidationError):
            BulkDockerRequest(node_ids=[], node_tags=[], container_id="abc")

    def test_bulk_response(self) -> None:
        resp = BulkDockerResponse(
            action="start",
            results=[],
            total=0,
            succeeded=0,
            failed=0,
        )
        assert resp.action == "start"
        assert resp.total == 0


# --- DockerService bulk operations tests ---


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


class TestDockerServiceBulk:
    @pytest.mark.asyncio
    async def test_bulk_container_action_start(self) -> None:
        """bulk_container_action with start action."""
        from tests.docker_test_facade import DockerService

        mock_repo = AsyncMock()
        mock_audit = AsyncMock()
        mock_factory = MagicMock()

        # Mock node
        mock_node = MagicMock()
        mock_node.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_node.name = "server1"
        mock_node.connection_type = "docker"
        mock_node.host = "10.0.0.1"
        mock_node.port = 22
        mock_node.username = "root"
        mock_node.password = None
        mock_node.ssh_key = None
        mock_node.docker_host = None

        mock_repo.get_by_id.return_value = mock_node

        # Mock connector
        mock_connector = AsyncMock()
        mock_connector.execute_command.return_value = ("", "", 0)
        mock_factory.create_ssh.return_value = MockAsyncContextManager(mock_connector)

        service = DockerService(
            repository=mock_repo,
            audit_service=mock_audit,
            connector_factory=mock_factory,
        )

        result = await service.bulk_container_action(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            action="start",
        )

        assert result.action == "start"
        assert result.total == 1
        assert result.succeeded == 1
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_bulk_container_action_unknown_action(self) -> None:
        """bulk_container_action with unknown action."""
        from tests.docker_test_facade import DockerService

        mock_repo = AsyncMock()
        mock_audit = AsyncMock()
        mock_factory = MagicMock()

        mock_node = MagicMock()
        mock_node.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_node.name = "server1"
        mock_node.connection_type = "docker"

        mock_repo.get_by_id.return_value = mock_node

        service = DockerService(
            repository=mock_repo,
            audit_service=mock_audit,
            connector_factory=mock_factory,
        )

        result = await service.bulk_container_action(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            action="unknown",
        )

        assert result.failed == 1
        assert "Unknown action" in result.results[0].error

    @pytest.mark.asyncio
    async def test_bulk_exec_success(self) -> None:
        """bulk_exec with successful execution."""
        from tests.docker_test_facade import DockerService

        mock_repo = AsyncMock()
        mock_audit = AsyncMock()
        mock_factory = MagicMock()

        mock_node = MagicMock()
        mock_node.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_node.name = "server1"
        mock_node.connection_type = "docker"
        mock_node.host = "10.0.0.1"
        mock_node.port = 22
        mock_node.username = "root"
        mock_node.password = None
        mock_node.ssh_key = None
        mock_node.docker_host = None

        mock_repo.get_by_id.return_value = mock_node

        mock_connector = AsyncMock()
        mock_connector.execute_command.return_value = ("hello", "", 0)
        mock_factory.create_ssh.return_value = MockAsyncContextManager(mock_connector)

        service = DockerService(
            repository=mock_repo,
            audit_service=mock_audit,
            connector_factory=mock_factory,
        )

        result = await service.bulk_exec(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            command="echo hello",
        )

        assert result.action == "exec"
        assert result.total == 1
        assert result.succeeded == 1
        assert result.results[0].output == "hello"


# ---------------------------------------------------------------------------
# DockerBulkService unit tests — covering _prepare error paths and worker errors
# ---------------------------------------------------------------------------


def _make_node(node_id: str = "00000000-0000-0000-0000-000000000001") -> MagicMock:
    """Return a mock NodeConnectionDTO."""
    mock_node = MagicMock()
    mock_node.id = uuid.UUID(node_id)
    mock_node.name = "server1"
    mock_node.connection_type = "docker"
    mock_node.host = "10.0.0.1"
    mock_node.port = 22
    mock_node.username = "root"
    mock_node.password = None
    mock_node.ssh_key = None
    mock_node.docker_host = None
    return mock_node


def _make_runner(node: MagicMock | None = None) -> AsyncMock:
    """Return a mock DockerCommandRunner."""
    runner = AsyncMock()
    runner.get_target = AsyncMock(return_value=node or _make_node())
    runner.build_command = MagicMock(return_value="docker ps")
    runner.execute = AsyncMock(return_value=("", "", 0))
    return runner


class TestBulkServicePrepareErrors:
    """Cover the _prepare error paths of DockerBulkService."""

    @pytest.mark.asyncio
    async def test_prepare_node_not_found(self) -> None:
        """A missing node produces an error result, not an exception."""
        from app.core.exceptions import NodeNotFoundError

        runner = _make_runner()
        runner.get_target = AsyncMock(side_effect=NodeNotFoundError("not found"))
        service = DockerBulkService(runner)

        result = await service.bulk_container_action(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            action="start",
        )
        assert result.failed == 1
        assert "not found" in result.results[0].error

    @pytest.mark.asyncio
    async def test_prepare_invalid_uuid(self) -> None:
        """A malformed UUID produces a ValueError error result."""

        runner = _make_runner()
        runner.get_target = AsyncMock(side_effect=ValueError("bad uuid"))
        service = DockerBulkService(runner)

        result = await service.bulk_container_action(
            node_ids=["not-a-uuid"],
            container_id="abc123def456",
            action="start",
        )
        assert result.failed == 1
        assert "badly formed" in result.results[0].error


class TestBulkServiceContainerActionBranches:
    """Cover stop/restart action and stderr error paths."""

    @pytest.mark.asyncio
    async def test_stop_action_success(self) -> None:
        """Stop action builds the right command and succeeds."""
        runner = _make_runner()
        service = DockerBulkService(runner)

        result = await service.bulk_container_action(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            action="stop",
            timeout=15,
        )
        assert result.succeeded == 1
        # Ensure stop with timeout was called
        called_args = runner.build_command.call_args[0][1]
        assert "stop" in called_args
        assert "15" in called_args

    @pytest.mark.asyncio
    async def test_restart_action_success(self) -> None:
        """Restart action builds the right command and succeeds."""
        runner = _make_runner()
        service = DockerBulkService(runner)

        result = await service.bulk_container_action(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            action="restart",
            timeout=20,
        )
        assert result.succeeded == 1

    @pytest.mark.asyncio
    async def test_nonzero_exit_with_stderr(self) -> None:
        """Non-zero exit code with stderr produces an error result."""
        runner = _make_runner()
        runner.execute = AsyncMock(return_value=("", "container not found", 1))
        service = DockerBulkService(runner)

        result = await service.bulk_container_action(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            action="start",
        )
        assert result.failed == 1
        assert "container not found" in result.results[0].error


class TestBulkServiceExecErrors:
    """Cover bulk_exec worker exception path."""

    @pytest.mark.asyncio
    async def test_exec_worker_exception(self) -> None:
        """Worker exception during exec is caught and reported as error."""
        runner = _make_runner()
        runner.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
        service = DockerBulkService(runner)

        result = await service.bulk_exec(
            node_ids=["00000000-0000-0000-0000-000000000001"],
            container_id="abc123def456",
            command="echo hello",
        )
        assert result.failed == 1
        assert "connection lost" in result.results[0].error
