"""Integration tests for SSH connector with a real Docker SSH server."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.connectors.ssh import SSHConnector
from app.models.node import NodeModel
from app.schemas.node import CommandRequest
from app.services.node_service import NodeService
from tests.integration_ssh.conftest import SSHServer


def _connector(ssh_server: SSHServer) -> SSHConnector:
    return SSHConnector(
        host=ssh_server.host,
        port=ssh_server.port,
        username=ssh_server.username,
        password=ssh_server.password,
        known_hosts=None,
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
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


@pytest.mark.asyncio
async def test_connect_and_disconnect(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        assert connector._connection is not None
    assert connector._connection is None


@pytest.mark.asyncio
async def test_execute_simple_command(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        stdout, stderr, exit_code = await connector.execute_command("echo hello")
    assert stdout.strip() == "hello"
    assert stderr == ""
    assert exit_code == 0


@pytest.mark.asyncio
async def test_execute_command_with_exit_code(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        stdout, stderr, exit_code = await connector.execute_command("exit 1")
    assert stdout == ""
    assert exit_code != 0


@pytest.mark.asyncio
async def test_execute_multiple_commands(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        r1, _, _ = await connector.execute_command("echo first")
        r2, _, _ = await connector.execute_command("echo second")
    assert r1.strip() == "first"
    assert r2.strip() == "second"


@pytest.mark.asyncio
async def test_service_check_connectivity(ssh_server: SSHServer) -> None:
    orm_node = _make_orm_node(ssh_server)
    repo = AsyncMock()
    repo.get_by_id.return_value = orm_node
    repo.update.return_value = orm_node

    factory = _make_connector_factory(ssh_server)
    service = NodeService(repository=repo, connector_factory=factory)

    result = await service.check_connectivity(orm_node.id)

    assert result.status == "active"
    repo.update.assert_called_once_with(orm_node.id, {"status": "active"})


@pytest.mark.asyncio
async def test_service_execute_command(ssh_server: SSHServer) -> None:
    orm_node = _make_orm_node(ssh_server)
    repo = AsyncMock()
    repo.get_by_id.return_value = orm_node

    factory = _make_connector_factory(ssh_server)
    service = NodeService(repository=repo, connector_factory=factory)

    result = await service.execute_command(
        orm_node.id, CommandRequest(command="echo works")
    )

    assert result.stdout.strip() == "works"
    assert result.exit_code == 0
