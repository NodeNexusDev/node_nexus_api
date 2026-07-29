"""Integration tests for Docker operations via SSH."""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.connectors.ssh import SSHConnector
from app.models.node import NodeModel
from app.services.docker_service import DockerService
from tests.integration.conftest import DockerSSHServer


def _connector(ssh_server: DockerSSHServer) -> SSHConnector:
    return SSHConnector(
        host=ssh_server.host,
        port=ssh_server.port,
        username=ssh_server.username,
        password=ssh_server.password,
        known_hosts=None,
        strict_host_key_checking=False,
    )


def _make_connector_factory(ssh_server: DockerSSHServer) -> AsyncMock:
    factory = AsyncMock()
    factory.create_ssh = Mock(return_value=_connector(ssh_server))
    return factory


def _make_orm_node(ssh_server: DockerSSHServer, **overrides: Any) -> NodeModel:
    defaults = {
        "id": uuid.uuid4(),
        "name": "test-docker-node",
        "host": ssh_server.host,
        "port": ssh_server.port,
        "connection_type": "docker",
        "status": "active",
        "username": ssh_server.username,
        "password": None,
        "ssh_key": None,
        "docker_host": None,
        "tags": [],
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


@pytest.mark.docker
class TestDockerIntegration:
    async def test_connect_to_docker_host(
        self, docker_ssh_server: DockerSSHServer
    ) -> None:
        """Test SSH connection to Docker host."""
        connector = _connector(docker_ssh_server)
        async with connector:
            assert connector._connection is not None

    async def test_docker_info(self, docker_ssh_server: DockerSSHServer) -> None:
        """Test that docker info returns data."""
        connector = _connector(docker_ssh_server)
        async with connector:
            stdout, stderr, exit_code = await connector.execute_command(
                "docker info --format '{{json .}}'"
            )
        assert exit_code == 0
        data = json.loads(stdout)
        assert "ServerVersion" in data

    async def test_list_containers_empty(
        self, docker_ssh_server: DockerSSHServer
    ) -> None:
        """Test listing containers when none exist."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        containers = await service.list_containers(orm_node.id)
        assert isinstance(containers, list)

    async def test_run_and_list_container(
        self, docker_ssh_server: DockerSSHServer
    ) -> None:
        """Test running a container and listing it."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        # Run a container
        connector = _connector(docker_ssh_server)
        async with connector:
            stdout, _, exit_code = await connector.execute_command(
                "docker run -d alpine:latest sleep 300"
            )
        assert exit_code == 0
        container_id = stdout.strip()

        try:
            # List containers
            containers = await service.list_containers(orm_node.id)
            assert len(containers) >= 1
            assert any(c.id.startswith(container_id[:12]) for c in containers)
        finally:
            # Cleanup
            async with connector:
                await connector.execute_command(f"docker rm -f {container_id}")

    async def test_exec_in_container(self, docker_ssh_server: DockerSSHServer) -> None:
        """Test executing a command in a container."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        # Run a container
        connector = _connector(docker_ssh_server)
        async with connector:
            stdout, _, exit_code = await connector.execute_command(
                "docker run -d alpine:latest sleep 300"
            )
        container_id = stdout.strip()

        try:
            # Exec in container
            result = await service.exec_command(orm_node.id, container_id, "echo hello")
            assert result.stdout.strip() == "hello"
            assert result.exit_code == 0
        finally:
            # Cleanup
            async with connector:
                await connector.execute_command(f"docker rm -f {container_id}")

    async def test_get_container_logs(self, docker_ssh_server: DockerSSHServer) -> None:
        """Test getting container logs."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        # Run a container that outputs something
        connector = _connector(docker_ssh_server)
        async with connector:
            stdout, _, exit_code = await connector.execute_command(
                'docker run -d alpine:latest sh -c "echo test_log_line && sleep 300"'
            )
        container_id = stdout.strip()

        try:
            # Wait a bit for the log to be written
            async with connector:
                await connector.execute_command("sleep 1")

            # Get logs
            logs = await service.get_logs(orm_node.id, container_id)
            assert "test_log_line" in logs
        finally:
            # Cleanup
            async with connector:
                await connector.execute_command(f"docker rm -f {container_id}")

    async def test_stop_start_container(
        self, docker_ssh_server: DockerSSHServer
    ) -> None:
        """Test stopping and starting a container."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        # Run a container
        connector = _connector(docker_ssh_server)
        async with connector:
            stdout, _, exit_code = await connector.execute_command(
                "docker run -d alpine:latest sleep 300"
            )
        container_id = stdout.strip()

        try:
            # Stop container
            await service.stop_container(orm_node.id, container_id)

            # Verify it's stopped
            async with connector:
                stdout, _, _ = await connector.execute_command(
                    f"docker inspect --format '{{{{.State.Running}}}}' {container_id}"
                )
            assert stdout.strip() == "false"

            # Start container
            await service.start_container(orm_node.id, container_id)

            # Verify it's running
            async with connector:
                stdout, _, _ = await connector.execute_command(
                    f"docker inspect --format '{{{{.State.Running}}}}' {container_id}"
                )
            assert stdout.strip() == "true"
        finally:
            # Cleanup
            async with connector:
                await connector.execute_command(f"docker rm -f {container_id}")

    async def test_remove_container(self, docker_ssh_server: DockerSSHServer) -> None:
        """Test removing a container."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        # Run a container
        connector = _connector(docker_ssh_server)
        async with connector:
            stdout, _, exit_code = await connector.execute_command(
                "docker run -d alpine:latest sleep 300"
            )
        container_id = stdout.strip()

        # Remove container
        await service.remove_container(orm_node.id, container_id, force=True)

        # Verify it's gone
        async with connector:
            stdout, _, exit_code = await connector.execute_command(
                f"docker inspect {container_id}"
            )
        assert exit_code != 0

    async def test_list_images(self, docker_ssh_server: DockerSSHServer) -> None:
        """Test listing images."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        # Pull an image first
        connector = _connector(docker_ssh_server)
        async with connector:
            await connector.execute_command("docker pull alpine:latest")

        # List images
        images = await service.list_images(orm_node.id)
        assert isinstance(images, list)
        assert any(img.repository == "alpine" for img in images)

    async def test_list_networks(self, docker_ssh_server: DockerSSHServer) -> None:
        """Test listing networks."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        networks = await service.list_networks(orm_node.id)
        assert isinstance(networks, list)
        assert any(n.name == "bridge" for n in networks)

    async def test_list_volumes(self, docker_ssh_server: DockerSSHServer) -> None:
        """Test listing volumes."""
        orm_node = _make_orm_node(docker_ssh_server)
        repo = AsyncMock()
        repo.get_by_id.return_value = orm_node

        factory = _make_connector_factory(docker_ssh_server)
        service = DockerService(repository=repo, connector_factory=factory)

        volumes = await service.list_volumes(orm_node.id)
        assert isinstance(volumes, list)
