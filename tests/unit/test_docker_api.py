"""Unit tests for Docker API endpoints with mocked service via dishka."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.api.v1.docker import router as docker_router
from app.api.v1.health import router as health_router
from app.application.dto.docker import (
    ContainerCreatedDTO,
    DockerContainerConfigDTO,
    DockerContainerInspectDTO,
    DockerContainerStateDTO,
    DockerImageBuildResultDTO,
    DockerImageInspectDTO,
    DockerImageTagResultDTO,
)
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.docker.image_service import DockerImageService
from app.application.services.docker.resource_service import DockerResourceService
from app.core.exceptions import (
    ConnectionFailedError,
    ContainerNotFoundError,
    DockerError,
    DockerValidationError,
    DomainError,
    NodeNotFoundError,
)
from app.schemas.docker import (
    DockerContainer,
    DockerExecResult,
    DockerImage,
    DockerNetwork,
    DockerPullResult,
    DockerStats,
    DockerVolume,
)
from tests.docker_test_facade import DockerService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings

NODE_ID = uuid.uuid4()
CONTAINER_ID = "abc123def456"


# --- Response factories ---


def _make_container(**overrides: Any) -> DockerContainer:
    defaults: dict[str, Any] = {
        "ID": CONTAINER_ID,
        "Names": "/web",
        "Image": "nginx:latest",
        "Command": "nginx",
        "CreatedAt": "2026-01-01",
        "State": "running",
        "Status": "Up 5 days",
    }
    defaults.update(overrides)
    return DockerContainer(**defaults)


def _make_container_inspect(**overrides: Any) -> DockerContainerInspectDTO:
    defaults: dict[str, Any] = {
        "id": CONTAINER_ID,
        "name": "/web",
        "state": DockerContainerStateDTO(
            status="running",
            running=True,
            exit_code=0,
        ),
        "config": DockerContainerConfigDTO(image="nginx:latest"),
        "network_settings": (("Networks", {"bridge": {}}),),
    }
    defaults.update(overrides)
    return DockerContainerInspectDTO(**defaults)


def _make_image(**overrides: Any) -> DockerImage:
    defaults: dict[str, Any] = {
        "Repository": "nginx",
        "Tag": "latest",
        "ID": "abc123def456",
        "Size": "187MB",
        "CreatedAt": "2025-07-01 00:00:00 +0000 UTC",
    }
    defaults.update(overrides)
    return DockerImage(**defaults)


def _make_stats(**overrides: Any) -> DockerStats:
    defaults: dict[str, Any] = {
        "Container": CONTAINER_ID,
        "Name": "web",
        "CPUPerc": "1.23%",
        "MemUsage": "100MiB",
        "MemPerc": "5.0%",
        "NetIO": "1MB / 2MB",
        "BlockIO": "0B / 0B",
        "PIDs": "1",
    }
    defaults.update(overrides)
    return DockerStats(**defaults)


def _make_network(**overrides: Any) -> DockerNetwork:
    defaults: dict[str, Any] = {
        "ID": "net123",
        "Name": "bridge",
        "Driver": "bridge",
        "Scope": "local",
    }
    defaults.update(overrides)
    return DockerNetwork(**defaults)


def _make_volume(**overrides: Any) -> DockerVolume:
    defaults: dict[str, Any] = {
        "Driver": "local",
        "Name": "myvolume",
    }
    defaults.update(overrides)
    return DockerVolume(**defaults)


def _make_exec_result(**overrides: Any) -> DockerExecResult:
    defaults: dict[str, Any] = {
        "stdout": "output",
        "stderr": "",
        "exit_code": 0,
    }
    defaults.update(overrides)
    return DockerExecResult(**defaults)


def _make_pull_result(**overrides: Any) -> DockerPullResult:
    defaults: dict[str, Any] = {
        "image": "nginx:latest",
        "output": "Status: Downloaded newer image",
        "success": True,
    }
    defaults.update(overrides)
    return DockerPullResult(**defaults)


# --- App setup ---


def _create_test_app(service: DockerService | AsyncMock) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(health_router)
    app.include_router(docker_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_container_service(self) -> DockerContainerService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_image_service(self) -> DockerImageService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_resource_service(self) -> DockerResourceService:
            return service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=DockerService)


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


@pytest.fixture
def full_service() -> AsyncMock:
    """An unrestricted mock exposing the new image/container service methods."""
    return AsyncMock()


@pytest.fixture
async def full_client(full_service: AsyncMock) -> AsyncGenerator[AsyncClient]:
    app = _create_test_app(full_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


# --- GET /nodes/{node_id}/docker/containers ---


class TestListContainers:
    async def test_returns_containers(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_containers.return_value = [_make_container()]
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/containers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ID"] == CONTAINER_ID

    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_containers.return_value = []
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/containers")
        assert response.status_code == 200
        assert response.json() == []

    async def test_query_param_all(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_containers.return_value = []
        await client.get(f"/api/v1/nodes/{NODE_ID}/docker/containers?all=true")
        mock_service.list_containers.assert_called_once_with(NODE_ID, all=True)

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_containers.side_effect = NodeNotFoundError("not found")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/containers")
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_containers.side_effect = DockerError("daemon error")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/containers")
        assert response.status_code == 502


# --- GET /nodes/{node_id}/docker/containers/{container_id} ---


class TestGetContainer:
    async def test_returns_container(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_container.return_value = _make_container_inspect()
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 200
        assert response.json()["Id"] == CONTAINER_ID
        assert response.json()["NetworkSettings"] == {"Networks": {"bridge": {}}}

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_container.side_effect = NodeNotFoundError("not found")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_container.side_effect = ContainerNotFoundError("not found")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 404

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_container.side_effect = DockerValidationError("invalid")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 422

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_container.side_effect = DockerError("daemon error")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 502


# --- POST /nodes/{node_id}/docker/containers/{container_id}/start ---


class TestStartContainer:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.start_container.return_value = None
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/start"
        )
        assert response.status_code == 204

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.start_container.side_effect = NodeNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/start"
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.start_container.side_effect = ContainerNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/start"
        )
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.start_container.side_effect = DockerError("error")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/start"
        )
        assert response.status_code == 502


# --- POST /nodes/{node_id}/docker/containers/{container_id}/stop ---


class TestStopContainer:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.stop_container.return_value = None
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stop"
        )
        assert response.status_code == 204

    async def test_query_param_timeout(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.stop_container.return_value = None
        await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stop?timeout=30"
        )
        mock_service.stop_container.assert_called_once_with(
            NODE_ID, CONTAINER_ID, timeout=30
        )

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.stop_container.side_effect = NodeNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stop"
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.stop_container.side_effect = ContainerNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stop"
        )
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.stop_container.side_effect = DockerError("error")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stop"
        )
        assert response.status_code == 502


# --- POST /nodes/{node_id}/docker/containers/{container_id}/restart ---


class TestRestartContainer:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.restart_container.return_value = None
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/restart"
        )
        assert response.status_code == 204

    async def test_query_param_timeout(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.restart_container.return_value = None
        await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/restart?timeout=5"
        )
        mock_service.restart_container.assert_called_once_with(
            NODE_ID, CONTAINER_ID, timeout=5
        )

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.restart_container.side_effect = NodeNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/restart"
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.restart_container.side_effect = ContainerNotFoundError("nf")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/restart"
        )
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.restart_container.side_effect = DockerError("error")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/restart"
        )
        assert response.status_code == 502


# --- DELETE /nodes/{node_id}/docker/containers/{container_id} ---


class TestRemoveContainer:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.remove_container.return_value = None
        response = await client.delete(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 204

    async def test_query_param_force(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.remove_container.return_value = None
        await client.delete(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}?force=true"
        )
        mock_service.remove_container.assert_called_once_with(
            NODE_ID, CONTAINER_ID, force=True
        )

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.remove_container.side_effect = NodeNotFoundError("not found")
        response = await client.delete(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.remove_container.side_effect = ContainerNotFoundError("nf")
        response = await client.delete(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.remove_container.side_effect = DockerError("error")
        response = await client.delete(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}"
        )
        assert response.status_code == 502


# --- GET /nodes/{node_id}/docker/containers/{container_id}/logs ---


class TestGetLogs:
    async def test_returns_logs(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.return_value = "log line 1\nlog line 2"
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/logs"
        )
        assert response.status_code == 200
        assert "log line 1" in response.json()

    async def test_query_params(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.return_value = ""
        await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/logs?tail=50&since=12345"
        )
        mock_service.get_logs.assert_called_once_with(
            NODE_ID, CONTAINER_ID, tail=50, since="12345"
        )

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.side_effect = NodeNotFoundError("not found")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/logs"
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.side_effect = ContainerNotFoundError("nf")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/logs"
        )
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.side_effect = DockerError("error")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/logs"
        )
        assert response.status_code == 502


# --- POST /nodes/{node_id}/docker/containers/{container_id}/exec ---


class TestExecCommand:
    async def test_returns_result(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.exec_command.return_value = _make_exec_result()
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/exec",
            json={"command": "echo hello"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stdout"] == "output"
        assert data["exit_code"] == 0

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.exec_command.side_effect = NodeNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/exec",
            json={"command": "ls"},
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.exec_command.side_effect = ContainerNotFoundError("nf")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/exec",
            json={"command": "ls"},
        )
        assert response.status_code == 404

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.exec_command.side_effect = DockerValidationError("invalid")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/exec",
            json={"command": "ls"},
        )
        assert response.status_code == 422

    async def test_connection_failed(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.exec_command.side_effect = ConnectionFailedError("refused")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/exec",
            json={"command": "ls"},
        )
        assert response.status_code == 503

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.exec_command.side_effect = DockerError("error")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/exec",
            json={"command": "ls"},
        )
        assert response.status_code == 502

    async def test_validation_error_missing_command(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/exec",
            json={},
        )
        assert response.status_code == 422


# --- GET /nodes/{node_id}/docker/containers/{container_id}/stats ---


class TestGetStats:
    async def test_returns_stats(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_stats.return_value = _make_stats()
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stats"
        )
        assert response.status_code == 200
        assert response.json()["Container"] == CONTAINER_ID

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_stats.side_effect = NodeNotFoundError("not found")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stats"
        )
        assert response.status_code == 404

    async def test_container_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_stats.side_effect = ContainerNotFoundError("nf")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stats"
        )
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_stats.side_effect = DockerError("error")
        response = await client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/containers/{CONTAINER_ID}/stats"
        )
        assert response.status_code == 502


# --- GET /nodes/{node_id}/docker/images ---


class TestListImages:
    async def test_returns_images(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_images.return_value = [_make_image()]
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/images")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["Repository"] == "nginx"

    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_images.return_value = []
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/images")
        assert response.status_code == 200
        assert response.json() == []

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_images.side_effect = NodeNotFoundError("not found")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/images")
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_images.side_effect = DockerError("daemon error")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/images")
        assert response.status_code == 502


# --- POST /nodes/{node_id}/docker/images/pull ---


class TestPullImage:
    async def test_returns_result(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.pull_image.return_value = _make_pull_result()
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/pull",
            json={"image": "nginx:latest"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["image"] == "nginx:latest"

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.pull_image.side_effect = NodeNotFoundError("not found")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/pull",
            json={"image": "nginx:latest"},
        )
        assert response.status_code == 404

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.pull_image.side_effect = DockerValidationError("invalid")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/pull",
            json={"image": "nginx:latest"},
        )
        assert response.status_code == 422

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.pull_image.side_effect = DockerError("error")
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/pull",
            json={"image": "nginx:latest"},
        )
        assert response.status_code == 502

    async def test_validation_error_missing_image(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/pull",
            json={},
        )
        assert response.status_code == 422


# --- GET /nodes/{node_id}/docker/networks ---


class TestListNetworks:
    async def test_returns_networks(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_networks.return_value = [_make_network()]
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/networks")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["Name"] == "bridge"

    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_networks.return_value = []
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/networks")
        assert response.status_code == 200
        assert response.json() == []

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_networks.side_effect = NodeNotFoundError("not found")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/networks")
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_networks.side_effect = DockerError("daemon error")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/networks")
        assert response.status_code == 502


# --- GET /nodes/{node_id}/docker/volumes ---


class TestListVolumes:
    async def test_returns_volumes(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_volumes.return_value = [_make_volume()]
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/volumes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["Name"] == "myvolume"

    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_volumes.return_value = []
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/volumes")
        assert response.status_code == 200
        assert response.json() == []

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_volumes.side_effect = NodeNotFoundError("not found")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/volumes")
        assert response.status_code == 404

    async def test_docker_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.list_volumes.side_effect = DockerError("daemon error")
        response = await client.get(f"/api/v1/nodes/{NODE_ID}/docker/volumes")
        assert response.status_code == 502


# --- POST /nodes/{node_id}/docker/containers ---


class TestCreateContainer:
    async def test_success(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.create_container.return_value = ContainerCreatedDTO(
            id="abc123def456", name="my-ctr", image="alpine:latest", status="created"
        )
        response = await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers",
            json={"image": "alpine:latest", "name": "my-ctr", "command": "sleep 60"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "abc123def456"
        assert data["name"] == "my-ctr"
        assert data["image"] == "alpine:latest"
        assert data["status"] == "created"

    async def test_passes_ports_env_labels(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.create_container.return_value = ContainerCreatedDTO(
            id="abc", name="x", image="alpine", status="created"
        )
        await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers",
            json={
                "image": "alpine",
                "name": "x",
                "ports": {"80/tcp": "8080"},
                "env": ["FOO=bar"],
                "labels": {"app": "web"},
                "network": "bridge",
                "restart_policy": "always",
            },
        )
        full_service.create_container.assert_called_once()
        request_dto = full_service.create_container.call_args.args[0]
        assert request_dto.ports == (("80/tcp", "8080"),)
        assert request_dto.env == ("FOO=bar",)
        assert request_dto.labels == (("app", "web"),)
        assert request_dto.network == "bridge"
        assert request_dto.restart_policy == "always"

    async def test_missing_image_returns_422(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        response = await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers",
            json={"name": "x"},
        )
        assert response.status_code == 422

    async def test_docker_error(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.create_container.side_effect = DockerError("daemon error")
        response = await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/containers",
            json={"image": "alpine"},
        )
        assert response.status_code == 502


# --- GET /nodes/{node_id}/docker/images/{image_id} ---


class TestInspectImage:
    async def test_success(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.inspect_image.return_value = DockerImageInspectDTO(
            id="sha256:abc123",
            repo_tags=("alpine:latest",),
            size=7333821,
            created="2026-01-01T00:00:00Z",
            architecture="amd64",
            os="linux",
        )
        response = await full_client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/images/sha256:abc123"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "sha256:abc123"
        assert data["repo_tags"] == ["alpine:latest"]
        assert data["size"] == 7333821
        assert data["architecture"] == "amd64"

    async def test_image_not_found(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        from app.core.exceptions import ImageNotFoundError

        full_service.inspect_image.side_effect = ImageNotFoundError("not found")
        response = await full_client.get(
            f"/api/v1/nodes/{NODE_ID}/docker/images/missing:latest"
        )
        assert response.status_code == 404


# --- DELETE /nodes/{node_id}/docker/images/{image_id} ---


class TestRemoveImage:
    async def test_success(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.remove_image.return_value = None
        response = await full_client.delete(
            f"/api/v1/nodes/{NODE_ID}/docker/images/alpine:latest"
        )
        assert response.status_code == 204
        full_service.remove_image.assert_called_once_with(NODE_ID, "alpine:latest")

    async def test_image_not_found(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        from app.core.exceptions import ImageNotFoundError

        full_service.remove_image.side_effect = ImageNotFoundError("not found")
        response = await full_client.delete(
            f"/api/v1/nodes/{NODE_ID}/docker/images/missing:latest"
        )
        assert response.status_code == 404


# --- POST /nodes/{node_id}/docker/images/{image_id}/tag ---


class TestTagImage:
    async def test_success(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.tag_image.return_value = DockerImageTagResultDTO(
            source="alpine:latest", target="my-registry.com/app:v1.0"
        )
        response = await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/alpine:latest/tag",
            json={"repo": "my-registry.com/app", "tag": "v1.0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "alpine:latest"
        assert data["target"] == "my-registry.com/app:v1.0"

    async def test_missing_repo_returns_422(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        response = await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/alpine:latest/tag",
            json={"tag": "v1.0"},
        )
        assert response.status_code == 422


# --- POST /nodes/{node_id}/docker/images/build ---


class TestBuildImage:
    async def test_success(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.build_image.return_value = DockerImageBuildResultDTO(
            image_id="sha256:abcdef",
            tag="my-image:v1.0",
            output="Successfully built sha256:abcdef",
        )
        response = await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/build",
            json={
                "dockerfile": "FROM alpine:latest\nRUN echo hello",
                "tag": "my-image:v1.0",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["image_id"] == "sha256:abcdef"
        assert data["tag"] == "my-image:v1.0"

    async def test_passes_build_args_and_no_cache(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        full_service.build_image.return_value = DockerImageBuildResultDTO(
            image_id="", tag="img:1", output=""
        )
        await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/build",
            json={
                "dockerfile": "FROM alpine",
                "tag": "img:1",
                "build_args": {"VERSION": "1.0"},
                "no_cache": True,
            },
        )
        request_dto = full_service.build_image.call_args.args[0]
        assert request_dto.build_args == (("VERSION", "1.0"),)
        assert request_dto.no_cache is True

    async def test_missing_dockerfile_returns_422(
        self, full_client: AsyncClient, full_service: AsyncMock
    ) -> None:
        response = await full_client.post(
            f"/api/v1/nodes/{NODE_ID}/docker/images/build",
            json={"tag": "img:1"},
        )
        assert response.status_code == 422
