"""Integration tests for SSH connector with a real Docker SSH server."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.command_execution import CommandRequestDTO
from app.core.connectors.ssh import SSHConnector
from app.models.node import NodeModel
from app.services.node_command_service import NodeCommandService
from tests.integration_ssh.conftest import SSHServer


def _connector(ssh_server: SSHServer) -> SSHConnector:
    return SSHConnector(
        host=ssh_server.host,
        port=ssh_server.port,
        username=ssh_server.username,
        password=ssh_server.password,
        known_hosts=None,
        strict_host_key_checking=False,
    )


def _make_connector_factory(ssh_server: SSHServer) -> AsyncMock:
    factory = AsyncMock()
    factory.create_ssh = Mock(return_value=_connector(ssh_server))
    return factory


def _make_orm_node(ssh_server: SSHServer, **overrides: Any) -> NodeModel:
    defaults = {
        "id": uuid.uuid4(),
        "name": "test-ssh-node",
        "host": ssh_server.host,
        "port": ssh_server.port,
        "connection_type": "ssh",
        "status": "active",
        "username": ssh_server.username,
        "password": None,
        "ssh_key": None,
        "docker_host": None,
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


async def test_connect_and_disconnect(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        assert connector._connection is not None
    assert connector._connection is None


async def test_execute_simple_command(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        stdout, stderr, exit_code = await connector.execute_command("echo hello")
    assert stdout.strip() == "hello"
    assert stderr == ""
    assert exit_code == 0


async def test_execute_command_with_exit_code(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        stdout, stderr, exit_code = await connector.execute_command("exit 1")
    assert stdout == ""
    assert exit_code != 0


async def test_execute_multiple_commands(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        r1, _, _ = await connector.execute_command("echo first")
        r2, _, _ = await connector.execute_command("echo second")
    assert r1.strip() == "first"
    assert r2.strip() == "second"


async def test_service_check_connectivity(ssh_server: SSHServer) -> None:
    orm_node = _make_orm_node(ssh_server)
    repo = AsyncMock()
    repo.get_connection.return_value = orm_node
    repo.update_node_status.return_value = orm_node

    factory = _make_connector_factory(ssh_server)
    service = NodeCommandService(
        node_reader=repo,
        status_writer=repo,
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=factory,
    )

    result = await service.check_connectivity(orm_node.id)

    assert result.status == "active"
    repo.update_node_status.assert_called_once_with(orm_node.id, "active")


async def test_service_execute_command(ssh_server: SSHServer) -> None:
    orm_node = _make_orm_node(ssh_server)
    repo = AsyncMock()
    repo.get_connection.return_value = orm_node

    factory = _make_connector_factory(ssh_server)
    service = NodeCommandService(
        node_reader=repo,
        status_writer=repo,
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=factory,
    )

    result = await service.execute_command(
        orm_node.id, CommandRequestDTO(command="echo works")
    )

    assert result.stdout.strip() == "works"
    assert result.exit_code == 0
