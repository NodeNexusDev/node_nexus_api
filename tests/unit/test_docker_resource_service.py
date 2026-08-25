"""Unit tests for DockerResourceService network/volume CRUD methods."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.dto.docker import (
    NetworkConnectRequestDTO,
    NetworkCreateRequestDTO,
    NetworkDisconnectRequestDTO,
    VolumeCreateRequestDTO,
)
from app.application.services.docker.resource_service import DockerResourceService
from app.core.exceptions import (
    ConnectionFailedError,
    DockerError,
    DockerValidationError,
)

NODE = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_node() -> MagicMock:
    mock = MagicMock()
    mock.id = NODE
    mock.name = "docker-node"
    mock.connection_type = "docker"
    mock.docker_host = None
    return mock


def _make_runner(
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
) -> AsyncMock:
    runner = AsyncMock()
    runner.get_target = AsyncMock(return_value=_make_node())
    runner.build_command = MagicMock(side_effect=lambda n, args: f"docker {args}")
    runner.execute = AsyncMock(return_value=(stdout, stderr, exit_code))
    return runner


# ---------------------------------------------------------------------------
# Network create
# ---------------------------------------------------------------------------


class TestCreateNetwork:
    async def test_success_returns_id(self) -> None:
        runner = _make_runner(stdout="abc123def456\n")
        service = DockerResourceService(runner)
        result = await service.create_network(
            NetworkCreateRequestDTO(node_id=NODE, name="test-net")
        )
        assert result == "abc123def456"
        cmd_args = runner.build_command.call_args[0][1]
        assert "network create" in cmd_args
        assert "--driver" in cmd_args
        assert "bridge" in cmd_args

    async def test_with_custom_driver(self) -> None:
        runner = _make_runner(stdout="net123\n")
        service = DockerResourceService(runner)
        result = await service.create_network(
            NetworkCreateRequestDTO(node_id=NODE, name="test-net", driver="overlay")
        )
        assert result == "net123"
        cmd_args = runner.build_command.call_args[0][1]
        assert "overlay" in cmd_args

    async def test_with_subnet_and_gateway(self) -> None:
        runner = _make_runner(stdout="net123\n")
        service = DockerResourceService(runner)
        result = await service.create_network(
            NetworkCreateRequestDTO(
                node_id=NODE,
                name="test-net",
                subnet="172.20.0.0/16",
                gateway="172.20.0.1",
            )
        )
        assert result == "net123"
        cmd_args = runner.build_command.call_args[0][1]
        assert "--subnet" in cmd_args
        assert "172.20.0.0/16" in cmd_args
        assert "--gateway" in cmd_args
        assert "172.20.0.1" in cmd_args

    async def test_invalid_driver_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError, match="Invalid network driver"):
            await service.create_network(
                NetworkCreateRequestDTO(
                    node_id=NODE, name="test-net", driver="bad;driver"
                )
            )

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: cannot create network", exit_code=1)
        service = DockerResourceService(runner)
        with pytest.raises(DockerError):
            await service.create_network(
                NetworkCreateRequestDTO(node_id=NODE, name="test-net")
            )


# ---------------------------------------------------------------------------
# Network inspect
# ---------------------------------------------------------------------------


class TestInspectNetwork:
    async def test_success(self) -> None:
        inspect_json = (
            '[{"Id":"abc123","Name":"test-net","Driver":"bridge",'
            '"Scope":"local","IPAM":{"Config":[{"Subnet":"172.20.0.0/16",'
            '"Gateway":"172.20.0.1"}]}}]'
        )
        runner = _make_runner(stdout=inspect_json)
        service = DockerResourceService(runner)
        result = await service.inspect_network(NODE, "abc123")
        assert result.id == "abc123"
        assert result.name == "test-net"
        assert result.driver == "bridge"
        assert result.subnet == "172.20.0.0/16"
        assert result.gateway == "172.20.0.1"

    async def test_with_containers(self) -> None:
        inspect_json = (
            '[{"Id":"net1","Name":"test-net","Driver":"bridge",'
            '"Scope":"local","Containers":{'
            '"ctr1":{"Name":"web","IPv4Address":"172.20.0.2/16","IPv6Address":""}'
            '},"IPAM":{"Config":[{"Subnet":"172.20.0.0/16"}]}}]'
        )
        runner = _make_runner(stdout=inspect_json)
        service = DockerResourceService(runner)
        result = await service.inspect_network(NODE, "net1")
        assert len(result.containers) == 1
        assert result.containers[0][0] == "ctr1"
        assert result.containers[0][1]["Name"] == "web"

    async def test_empty_output_raises(self) -> None:
        runner = _make_runner(stdout="[]")
        service = DockerResourceService(runner)
        with pytest.raises(DockerError, match="not found"):
            await service.inspect_network(NODE, "abc123")

    async def test_invalid_network_id_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError):
            await service.inspect_network(NODE, "bad;id")

    async def test_connection_error_propagates(self) -> None:
        runner = _make_runner()
        runner.execute = AsyncMock(side_effect=ConnectionFailedError("ssh unreachable"))
        service = DockerResourceService(runner)
        with pytest.raises(ConnectionFailedError):
            await service.inspect_network(NODE, "abc123")


# ---------------------------------------------------------------------------
# Network remove
# ---------------------------------------------------------------------------


class TestRemoveNetwork:
    async def test_success(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        await service.remove_network(NODE, "abc123")
        cmd_args = runner.build_command.call_args[0][1]
        assert "network rm" in cmd_args
        assert "abc123" in cmd_args

    async def test_invalid_network_id_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError):
            await service.remove_network(NODE, "bad;id")

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: network not found", exit_code=1)
        service = DockerResourceService(runner)
        with pytest.raises(DockerError):
            await service.remove_network(NODE, "abc123")


# ---------------------------------------------------------------------------
# Network connect
# ---------------------------------------------------------------------------


class TestConnectToNetwork:
    async def test_success(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        await service.connect_to_network(
            NetworkConnectRequestDTO(
                node_id=NODE, network_id="net1", container_id="ctr1"
            )
        )
        cmd_args = runner.build_command.call_args[0][1]
        assert "network connect" in cmd_args
        assert "net1" in cmd_args
        assert "ctr1" in cmd_args

    async def test_with_ip_address(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        await service.connect_to_network(
            NetworkConnectRequestDTO(
                node_id=NODE,
                network_id="net1",
                container_id="ctr1",
                ip_address="172.20.0.5",
            )
        )
        cmd_args = runner.build_command.call_args[0][1]
        assert "--ip" in cmd_args
        assert "172.20.0.5" in cmd_args

    async def test_invalid_network_id_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError):
            await service.connect_to_network(
                NetworkConnectRequestDTO(
                    node_id=NODE, network_id="bad;id", container_id="ctr1"
                )
            )

    async def test_invalid_container_id_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError):
            await service.connect_to_network(
                NetworkConnectRequestDTO(
                    node_id=NODE, network_id="net1", container_id="bad;id"
                )
            )

    async def test_invalid_ip_address_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError, match="Invalid IP address"):
            await service.connect_to_network(
                NetworkConnectRequestDTO(
                    node_id=NODE,
                    network_id="net1",
                    container_id="ctr1",
                    ip_address="not-an-ip",
                )
            )

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: network not found", exit_code=1)
        service = DockerResourceService(runner)
        with pytest.raises(DockerError):
            await service.connect_to_network(
                NetworkConnectRequestDTO(
                    node_id=NODE, network_id="net1", container_id="ctr1"
                )
            )


# ---------------------------------------------------------------------------
# Network disconnect
# ---------------------------------------------------------------------------


class TestDisconnectFromNetwork:
    async def test_success(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        await service.disconnect_from_network(
            NetworkDisconnectRequestDTO(
                node_id=NODE, network_id="net1", container_id="ctr1"
            )
        )
        cmd_args = runner.build_command.call_args[0][1]
        assert "network disconnect" in cmd_args
        assert "net1" in cmd_args
        assert "ctr1" in cmd_args
        assert "--force" not in cmd_args

    async def test_with_force(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        await service.disconnect_from_network(
            NetworkDisconnectRequestDTO(
                node_id=NODE, network_id="net1", container_id="ctr1", force=True
            )
        )
        cmd_args = runner.build_command.call_args[0][1]
        assert "--force" in cmd_args

    async def test_invalid_network_id_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError):
            await service.disconnect_from_network(
                NetworkDisconnectRequestDTO(
                    node_id=NODE, network_id="bad;id", container_id="ctr1"
                )
            )

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: network not found", exit_code=1)
        service = DockerResourceService(runner)
        with pytest.raises(DockerError):
            await service.disconnect_from_network(
                NetworkDisconnectRequestDTO(
                    node_id=NODE, network_id="net1", container_id="ctr1"
                )
            )


# ---------------------------------------------------------------------------
# Volume create
# ---------------------------------------------------------------------------


class TestCreateVolume:
    async def test_success_auto_name(self) -> None:
        runner = _make_runner(stdout="abc123def456\n")
        service = DockerResourceService(runner)
        result = await service.create_volume(VolumeCreateRequestDTO(node_id=NODE))
        assert result == "abc123def456"
        cmd_args = runner.build_command.call_args[0][1]
        assert "volume create" in cmd_args

    async def test_with_name(self) -> None:
        runner = _make_runner(stdout="my-vol\n")
        service = DockerResourceService(runner)
        result = await service.create_volume(
            VolumeCreateRequestDTO(node_id=NODE, name="my-vol")
        )
        assert result == "my-vol"
        cmd_args = runner.build_command.call_args[0][1]
        assert "my-vol" in cmd_args

    async def test_with_custom_driver(self) -> None:
        runner = _make_runner(stdout="vol123\n")
        service = DockerResourceService(runner)
        result = await service.create_volume(
            VolumeCreateRequestDTO(node_id=NODE, driver="nfs")
        )
        assert result == "vol123"
        cmd_args = runner.build_command.call_args[0][1]
        assert "--driver" in cmd_args
        assert "nfs" in cmd_args

    async def test_local_driver_not_added(self) -> None:
        runner = _make_runner(stdout="vol123\n")
        service = DockerResourceService(runner)
        await service.create_volume(
            VolumeCreateRequestDTO(node_id=NODE, driver="local")
        )
        cmd_args = runner.build_command.call_args[0][1]
        assert "--driver" not in cmd_args

    async def test_invalid_name_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError, match="Invalid volume name"):
            await service.create_volume(
                VolumeCreateRequestDTO(node_id=NODE, name="bad;vol")
            )

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: volume create failed", exit_code=1)
        service = DockerResourceService(runner)
        with pytest.raises(DockerError):
            await service.create_volume(
                VolumeCreateRequestDTO(node_id=NODE, name="my-vol")
            )


# ---------------------------------------------------------------------------
# Volume inspect
# ---------------------------------------------------------------------------


class TestInspectVolume:
    async def test_success(self) -> None:
        inspect_json = (
            '[{"Name":"my-vol","Driver":"local",'
            '"Mountpoint":"/var/lib/docker/volumes/my-vol/_data",'
            '"Labels":{"app":"test"}}]'
        )
        runner = _make_runner(stdout=inspect_json)
        service = DockerResourceService(runner)
        result = await service.inspect_volume(NODE, "my-vol")
        assert result.name == "my-vol"
        assert result.driver == "local"
        assert result.mountpoint == "/var/lib/docker/volumes/my-vol/_data"
        assert ("app", "test") in result.labels

    async def test_no_labels(self) -> None:
        inspect_json = (
            '[{"Name":"vol1","Driver":"local","Mountpoint":"/data","Labels":null}]'
        )
        runner = _make_runner(stdout=inspect_json)
        service = DockerResourceService(runner)
        result = await service.inspect_volume(NODE, "vol1")
        assert result.labels == ()

    async def test_empty_output_raises(self) -> None:
        runner = _make_runner(stdout="[]")
        service = DockerResourceService(runner)
        with pytest.raises(DockerError, match="not found"):
            await service.inspect_volume(NODE, "my-vol")

    async def test_invalid_name_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError):
            await service.inspect_volume(NODE, "bad;vol")

    async def test_connection_error_propagates(self) -> None:
        runner = _make_runner()
        runner.execute = AsyncMock(side_effect=ConnectionFailedError("ssh unreachable"))
        service = DockerResourceService(runner)
        with pytest.raises(ConnectionFailedError):
            await service.inspect_volume(NODE, "my-vol")


# ---------------------------------------------------------------------------
# Volume remove
# ---------------------------------------------------------------------------


class TestRemoveVolume:
    async def test_success(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        await service.remove_volume(NODE, "my-vol")
        cmd_args = runner.build_command.call_args[0][1]
        assert "volume rm" in cmd_args
        assert "my-vol" in cmd_args

    async def test_invalid_name_raises(self) -> None:
        runner = _make_runner()
        service = DockerResourceService(runner)
        with pytest.raises(DockerValidationError):
            await service.remove_volume(NODE, "bad;vol")

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: volume not found", exit_code=1)
        service = DockerResourceService(runner)
        with pytest.raises(DockerError):
            await service.remove_volume(NODE, "my-vol")


# ---------------------------------------------------------------------------
# Volume prune
# ---------------------------------------------------------------------------


class TestPruneVolumes:
    async def test_success(self) -> None:
        runner = _make_runner(
            stdout="Deleted Volumes:\nabc123\nTotal reclaimed space: 1.5GB\n"
        )
        service = DockerResourceService(runner)
        result = await service.prune_volumes(NODE)
        assert "Deleted" in result
        assert "1.5GB" in result
        cmd_args = runner.build_command.call_args[0][1]
        assert "volume prune -f" in cmd_args

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: prune failed", exit_code=1)
        service = DockerResourceService(runner)
        with pytest.raises(DockerError):
            await service.prune_volumes(NODE)
