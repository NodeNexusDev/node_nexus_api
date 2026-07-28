"""Unit tests for Docker service."""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    ConnectionFailedError,
    ContainerNotFoundError,
    DockerDaemonError,
    DockerError,
    DockerValidationError,
    ImageNotFoundError,
    NodeNotFoundError,
)
from app.repositories.node_repo import NodeRepository
from app.services.docker_service import DockerService
from tests.unit.conftest import make_orm_node


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=NodeRepository)


@pytest.fixture
def mock_factory() -> MagicMock:
    factory = MagicMock()
    mock_connector = AsyncMock()
    mock_connector.execute_command.return_value = ("", "", 0)
    mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
    mock_connector.__aexit__ = AsyncMock(return_value=False)
    factory.create_ssh.return_value = mock_connector
    return factory


@pytest.fixture
def service(repo: AsyncMock, mock_factory: MagicMock) -> DockerService:
    return DockerService(repository=repo, connector_factory=mock_factory)


@pytest.fixture
def docker_node(repo: AsyncMock) -> Any:
    node = make_orm_node(
        connection_type="docker",
        docker_host="unix:///var/run/docker.sock",
    )
    repo.get_by_id.return_value = node
    return node


@pytest.fixture
def ssh_node(repo: AsyncMock) -> Any:
    node = make_orm_node(connection_type="ssh")
    repo.get_by_id.return_value = node
    return node


class TestGetDockerNode:
    async def test_returns_docker_node(
        self, service: DockerService, repo: AsyncMock, docker_node: Any
    ) -> None:
        result = await service._get_docker_node(docker_node.id)
        assert result.connection_type == "docker"

    async def test_raises_for_ssh_node(
        self, service: DockerService, repo: AsyncMock, ssh_node: Any
    ) -> None:
        with pytest.raises(DockerError, match="is not a Docker node"):
            await service._get_docker_node(ssh_node.id)

    async def test_raises_for_missing_node(
        self, service: DockerService, repo: AsyncMock
    ) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service._get_docker_node(uuid.uuid4())


class TestBuildDockerCmd:
    def test_with_docker_host(self, service: DockerService, docker_node: Any) -> None:
        cmd = service._build_docker_cmd(docker_node, "ps")
        assert "DOCKER_HOST=" in cmd
        assert "docker ps" in cmd

    def test_without_docker_host(self, service: DockerService, ssh_node: Any) -> None:
        cmd = service._build_docker_cmd(ssh_node, "ps")
        assert cmd == "docker ps"

    def test_special_chars_in_host(
        self, service: DockerService, repo: AsyncMock
    ) -> None:
        node = make_orm_node(
            connection_type="docker",
            docker_host="tcp://192.168.1.100:2376",
        )
        cmd = service._build_docker_cmd(node, "ps")
        assert "DOCKER_HOST=" in cmd
        assert "tcp://192.168.1.100:2376" in cmd


class TestParseJsonLines:
    def test_valid_json(self, service: DockerService) -> None:
        data = '{"ID":"abc","Names":"web"}'
        result = service._parse_json_lines(data)
        assert len(result) == 1
        assert result[0]["ID"] == "abc"

    def test_multiple_json_lines(self, service: DockerService) -> None:
        data = '{"ID":"abc","Names":"web"}\n{"ID":"def","Names":"api"}'
        result = service._parse_json_lines(data)
        assert len(result) == 2

    def test_mixed_output(self, service: DockerService) -> None:
        data = 'WARNING: some warning\n{"ID":"abc","Names":"web"}\nAnother warning'
        result = service._parse_json_lines(data)
        assert len(result) == 1

    def test_empty_lines(self, service: DockerService) -> None:
        data = '\n\n{"ID":"abc"}\n\n'
        result = service._parse_json_lines(data)
        assert len(result) == 1

    def test_malformed_json(self, service: DockerService) -> None:
        data = 'not json\n{"ID":"abc"}'
        result = service._parse_json_lines(data)
        assert len(result) == 1

    def test_empty_output(self, service: DockerService) -> None:
        result = service._parse_json_lines("")
        assert result == []


class TestParseJsonArray:
    def test_array_input(self, service: DockerService) -> None:
        data = '[{"Id":"abc","Name":"web"}]'
        result = service._parse_json_array(data)
        assert len(result) == 1
        assert result[0]["Id"] == "abc"

    def test_object_input(self, service: DockerService) -> None:
        data = '{"Id":"abc","Name":"web"}'
        result = service._parse_json_array(data)
        assert len(result) == 1

    def test_invalid_json(self, service: DockerService) -> None:
        result = service._parse_json_array("not json")
        assert result == []


class TestMapDockerError:
    def test_exit_code_zero(self, service: DockerService) -> None:
        # Should not raise
        service._map_docker_error("", 0)

    def test_no_such_container(self, service: DockerService) -> None:
        with pytest.raises(ContainerNotFoundError):
            service._map_docker_error("Error: No such container: abc", 1)

    def test_no_such_image(self, service: DockerService) -> None:
        with pytest.raises(ImageNotFoundError):
            service._map_docker_error("Error: No such image: nginx:latest", 1)

    def test_daemon_unreachable(self, service: DockerService) -> None:
        with pytest.raises(DockerDaemonError):
            service._map_docker_error("Cannot connect to the Docker daemon", 1)

    def test_container_not_running(self, service: DockerService) -> None:
        with pytest.raises(DockerError):
            service._map_docker_error(
                "Error response from daemon: container abc is not running", 1
            )

    def test_unknown_error(self, service: DockerService) -> None:
        with pytest.raises(DockerError, match="exit 1"):
            service._map_docker_error("Some unknown error", 1)


class TestListContainers:
    async def test_returns_parsed_containers(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        container_data = {
            "ID": "abc123",
            "Names": "web",
            "Image": "nginx:latest",
            "Command": "nginx",
            "CreatedAt": "2026-01-01",
            "State": "running",
            "Status": "Up 5 days",
        }
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            json.dumps(container_data),
            "",
            0,
        )
        result = await service.list_containers(docker_node.id)
        assert len(result) == 1
        assert result[0].id == "abc123"

    async def test_empty_output(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("", "", 0)
        result = await service.list_containers(docker_node.id)
        assert result == []

    async def test_non_docker_node_raises(
        self, service: DockerService, repo: AsyncMock, ssh_node: Any
    ) -> None:
        with pytest.raises(DockerError, match="is not a Docker node"):
            await service.list_containers(ssh_node.id)


class TestGetContainer:
    async def test_returns_inspect_data(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        inspect_data = [
            {
                "Id": "abc123",
                "Name": "/web",
                "State": {"Status": "running", "Running": True, "ExitCode": 0},
                "Config": {"Image": "nginx:latest"},
            }
        ]
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            json.dumps(inspect_data),
            "",
            0,
        )
        result = await service.get_container(docker_node.id, "abc123")
        assert result.id == "abc123"

    async def test_container_not_found(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            "",
            "Error: No such container: abc",
            1,
        )
        with pytest.raises(ContainerNotFoundError):
            await service.get_container(docker_node.id, "abc")

    async def test_invalid_container_id(
        self, service: DockerService, repo: AsyncMock, docker_node: Any
    ) -> None:
        with pytest.raises(DockerValidationError):
            await service.get_container(docker_node.id, "abc; rm -rf /")


class TestStartStopRestart:
    async def test_start_success(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("abc123", "", 0)
        await service.start_container(docker_node.id, "abc123")

    async def test_stop_with_timeout(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("abc123", "", 0)
        await service.stop_container(docker_node.id, "abc123", timeout=30)
        # Check that timeout was passed in the command
        call_args = mock_connector.execute_command.call_args[0][0]
        assert "-t 30" in call_args

    async def test_failure(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            "",
            "Error: No such container: abc",
            1,
        )
        with pytest.raises(ContainerNotFoundError):
            await service.start_container(docker_node.id, "abc")


class TestRemoveContainer:
    async def test_force_remove(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("abc123", "", 0)
        await service.remove_container(docker_node.id, "abc123", force=True)
        call_args = mock_connector.execute_command.call_args[0][0]
        assert "-f" in call_args

    async def test_invalid_container_id(
        self, service: DockerService, repo: AsyncMock, docker_node: Any
    ) -> None:
        with pytest.raises(DockerValidationError):
            await service.remove_container(docker_node.id, "invalid|id")


class TestGetLogs:
    async def test_returns_logs(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("log line 1\nlog line 2", "", 0)
        result = await service.get_logs(docker_node.id, "abc123")
        assert "log line 1" in result

    async def test_with_tail_param(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("logs", "", 0)
        await service.get_logs(docker_node.id, "abc123", tail=50)
        call_args = mock_connector.execute_command.call_args[0][0]
        assert "--tail 50" in call_args


class TestExecCommand:
    async def test_returns_result(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("output", "", 0)
        result = await service.exec_command(docker_node.id, "abc123", "echo hello")
        assert result.stdout == "output"
        assert result.exit_code == 0

    async def test_nonzero_exit(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("", "command not found", 127)
        result = await service.exec_command(docker_node.id, "abc123", "bad-cmd")
        assert result.exit_code == 127


class TestPullImage:
    async def test_success(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            "Pulling from library/nginx",
            "",
            0,
        )
        result = await service.pull_image(docker_node.id, "nginx:latest")
        assert result.success is True

    async def test_invalid_image_name(
        self, service: DockerService, repo: AsyncMock, docker_node: Any
    ) -> None:
        with pytest.raises(DockerValidationError):
            await service.pull_image(docker_node.id, "nginx; rm -rf /")


class TestListNetworks:
    async def test_returns_networks(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        network_data = {
            "ID": "abc123",
            "Name": "bridge",
            "Driver": "bridge",
            "Scope": "local",
        }
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            json.dumps(network_data),
            "",
            0,
        )
        result = await service.list_networks(docker_node.id)
        assert len(result) == 1
        assert result[0].name == "bridge"

    async def test_non_docker_node_raises(
        self, service: DockerService, repo: AsyncMock, ssh_node: Any
    ) -> None:
        with pytest.raises(DockerError, match="is not a Docker node"):
            await service.list_networks(ssh_node.id)

    async def test_empty_output(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("", "", 0)
        result = await service.list_networks(docker_node.id)
        assert result == []


class TestListVolumes:
    async def test_returns_volumes(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        volume_data = {"Driver": "local", "Name": "myvolume"}
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            json.dumps(volume_data),
            "",
            0,
        )
        result = await service.list_volumes(docker_node.id)
        assert len(result) == 1
        assert result[0].name == "myvolume"

    async def test_non_docker_node_raises(
        self, service: DockerService, repo: AsyncMock, ssh_node: Any
    ) -> None:
        with pytest.raises(DockerError, match="is not a Docker node"):
            await service.list_volumes(ssh_node.id)

    async def test_empty_output(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("", "", 0)
        result = await service.list_volumes(docker_node.id)
        assert result == []


class TestListImages:
    async def test_returns_images(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        image_data = {
            "Repository": "nginx",
            "Tag": "latest",
            "ID": "abc123def456",
            "Size": "187MB",
            "CreatedAt": "2025-07-01 00:00:00 +0000 UTC",
        }
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            json.dumps(image_data),
            "",
            0,
        )
        result = await service.list_images(docker_node.id)
        assert len(result) == 1
        assert result[0].repository == "nginx"

    async def test_non_docker_node_raises(
        self, service: DockerService, repo: AsyncMock, ssh_node: Any
    ) -> None:
        with pytest.raises(DockerError, match="is not a Docker node"):
            await service.list_images(ssh_node.id)

    async def test_empty_output(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("", "", 0)
        result = await service.list_images(docker_node.id)
        assert result == []

    async def test_docker_error(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            "",
            "Cannot connect to the Docker daemon",
            1,
        )
        with pytest.raises(DockerDaemonError):
            await service.list_images(docker_node.id)


class TestRestartContainer:
    async def test_restart(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("", "", 0)
        await service.restart_container(docker_node.id, "abc123", timeout=5)
        cmd = mock_connector.execute_command.call_args[0][0]
        assert "restart -t 5 abc123" in cmd


class TestGetContainerNotFound:
    async def test_docker_no_such_object(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            "",
            "Error response from daemon: No such object: nonexistent",
            1,
        )
        with pytest.raises(ContainerNotFoundError):
            await service.get_container(docker_node.id, "nonexistent")

    async def test_empty_inspect(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("[]", "", 0)
        with pytest.raises(ContainerNotFoundError):
            await service.get_container(docker_node.id, "abc123")


class TestPullImageConnectionFailed:
    async def test_returns_failure_result(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.side_effect = ConnectionFailedError(
            "Connection refused"
        )
        result = await service.pull_image(docker_node.id, "nginx")
        assert result.success is False
        assert "Connection refused" in result.output


class TestGetStats:
    async def test_returns_stats(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        stats_data = {
            "Container": "abc123",
            "Name": "web",
            "CPUPerc": "1.23%",
            "MemUsage": "100MiB",
            "MemPerc": "5.0%",
            "NetIO": "1MB / 2MB",
            "BlockIO": "0B / 0B",
            "PIDs": "1",
        }
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = (
            json.dumps(stats_data),
            "",
            0,
        )
        result = await service.get_stats(docker_node.id, "abc123")
        assert result.container_id == "abc123"

    async def test_empty_stats(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("", "", 0)
        with pytest.raises(ContainerNotFoundError):
            await service.get_stats(docker_node.id, "abc123")


class TestParseJsonLinesExtra:
    def test_skips_broken_json(self, service: DockerService) -> None:
        stdout = '{"a": 1}\nbroken json\n{"b": 2}\n'
        result = service._parse_json_lines(stdout)
        assert len(result) == 2
        assert result[0] == {"a": 1}
        assert result[1] == {"b": 2}

    def test_skips_non_json_lines(self, service: DockerService) -> None:
        stdout = 'pulling image...\n{"status": "done"}\n'
        result = service._parse_json_lines(stdout)
        assert len(result) == 1


class TestExecuteDockerCmdConnectionError:
    async def test_wraps_exception(
        self,
        service: DockerService,
        repo: AsyncMock,
        mock_factory: MagicMock,
        docker_node: Any,
    ) -> None:
        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.side_effect = OSError("Connection refused")
        with pytest.raises(ConnectionFailedError, match="Failed to connect"):
            await service._execute_docker_cmd(docker_node, "docker ps")


class TestLogWithAudit:
    async def test_calls_audit(
        self,
        repo: AsyncMock,
        mock_factory: MagicMock,
    ) -> None:
        audit_mock = AsyncMock()
        svc = DockerService(
            repository=repo, audit_service=audit_mock, connector_factory=mock_factory
        )
        await svc._log("test_action", node_id=uuid.uuid4(), details={"k": "v"})
        audit_mock.log.assert_awaited_once()
