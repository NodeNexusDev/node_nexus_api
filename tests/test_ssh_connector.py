"""Tests for SSH connector."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.connectors.ssh import SSHConnector


@pytest.fixture
def ssh_connector():
    """Create an SSHConnector instance."""
    return SSHConnector(
        host="192.168.1.100",
        port=22,
        username="testuser",
        password="testpass",
    )


async def test_ssh_connector_context_manager(ssh_connector):
    """Test SSHConnector as context manager."""
    with patch("app.core.connectors.ssh.asyncssh") as mock_ssh:
        mock_connection = AsyncMock()
        mock_ssh.connect = AsyncMock(return_value=mock_connection)

        async with ssh_connector as conn:
            assert conn is not None

        mock_connection.close.assert_called_once()


async def test_ssh_connector_execute_command(ssh_connector):
    """Test executing a command via SSH."""
    with patch("app.core.connectors.ssh.asyncssh") as mock_ssh:
        mock_connection = AsyncMock()
        mock_process = AsyncMock()
        mock_process.output = "test output"
        mock_connection.run = AsyncMock(return_value=mock_process)
        mock_ssh.connect = AsyncMock(return_value=mock_connection)

        async with ssh_connector as conn:
            result = await conn.execute_command("echo test")

        assert result == "test output"
