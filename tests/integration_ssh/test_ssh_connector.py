"""Integration tests for SSH connector with a real Docker SSH server."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.core.connectors.ssh import SSHConnector
from app.schemas.node import CommandRequest, NodeResponse
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


def _make_node(ssh_server: SSHServer) -> NodeResponse:
    return NodeResponse(
        id=uuid.uuid4(),
        name="test-ssh-node",
        host=ssh_server.host,
        port=ssh_server.port,
        connection_type="ssh",
        status="active",
        username=ssh_server.username,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


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
        result = await connector.execute_command("echo hello")
    assert result.strip() == "hello"


@pytest.mark.asyncio
async def test_execute_command_with_exit_code(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        result = await connector.execute_command("exit 1")
    assert result == ""


@pytest.mark.asyncio
async def test_execute_multiple_commands(ssh_server: SSHServer) -> None:
    connector = _connector(ssh_server)
    async with connector:
        r1 = await connector.execute_command("echo first")
        r2 = await connector.execute_command("echo second")
    assert r1.strip() == "first"
    assert r2.strip() == "second"


@pytest.mark.asyncio
async def test_service_check_connectivity(ssh_server: SSHServer) -> None:
    node = _make_node(ssh_server)
    repo = AsyncMock()
    repo.get_by_id.return_value = node
    repo.update.return_value = node

    service = NodeService(repository=repo)

    test_connector = _connector(ssh_server)
    with patch.object(service, "_build_connector", return_value=test_connector):
        result = await service.check_connectivity(node.id)

    assert result.status == "active"
    repo.update.assert_called_once_with(node.id, {"status": "active"})


@pytest.mark.asyncio
async def test_service_execute_command(ssh_server: SSHServer) -> None:
    node = _make_node(ssh_server)
    repo = AsyncMock()
    repo.get_by_id.return_value = node

    service = NodeService(repository=repo)

    test_connector = _connector(ssh_server)
    with patch.object(service, "_build_connector", return_value=test_connector):
        result = await service.execute_command(
            node.id, CommandRequest(command="echo works")
        )

    assert result.stdout.strip() == "works"
    assert result.exit_code == 0
