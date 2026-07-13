"""Unit tests for SSH connector edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.connectors.ssh import SSHConnector


class TestSSHConnector:
    @pytest.mark.asyncio
    async def test_not_connected_raises(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        with pytest.raises(RuntimeError, match="Not connected"):
            await connector.execute_command("echo hi")

    @pytest.mark.asyncio
    async def test_disconnect_without_connection(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        await connector.disconnect()
        assert connector._connection is None

    @pytest.mark.asyncio
    async def test_disconnect_with_connection(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()
        connector._connection = mock_conn
        await connector.disconnect()
        mock_conn.close.assert_called_once()
        mock_conn.wait_closed.assert_called_once()
        assert connector._connection is None

    @pytest.mark.asyncio
    async def test_key_auth_branch(self) -> None:
        key = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        connector = SSHConnector(
            host="127.0.0.1",
            ssh_key=key,
            known_hosts=None,
        )
        mock_conn = AsyncMock()
        connect_path = "app.core.connectors.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            await connector.connect()
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args
            assert "client_keys" in call_kwargs[1]
            assert connector._connection is mock_conn

    @pytest.mark.asyncio
    async def test_password_auth_branch(self) -> None:
        connector = SSHConnector(
            host="127.0.0.1",
            password="secret",
            known_hosts=None,
        )
        mock_conn = AsyncMock()
        connect_path = "app.core.connectors.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            await connector.connect()
            call_kwargs = mock_connect.call_args
            assert "password" in call_kwargs[1]
            assert call_kwargs[1]["password"] == "secret"

    @pytest.mark.asyncio
    async def test_execute_command_returns_tuple(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.exit_status = 0
        mock_conn.run = AsyncMock(return_value=mock_result)
        connector._connection = mock_conn

        stdout, stderr, exit_code = await connector.execute_command("echo hi")
        assert stdout == "output"
        assert stderr == ""
        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_command_non_zero_exit(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "command not found"
        mock_result.exit_status = 127
        mock_conn.run = AsyncMock(return_value=mock_result)
        connector._connection = mock_conn

        stdout, stderr, exit_code = await connector.execute_command("bad-cmd")
        assert exit_code == 127
        assert "not found" in stderr

    @pytest.mark.asyncio
    async def test_context_manager_calls_connect_disconnect(self) -> None:
        connector = SSHConnector(host="127.0.0.1", known_hosts=None)
        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        connect_path = "app.core.connectors.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            async with connector:
                assert connector._connection is mock_conn
            mock_conn.close.assert_called_once()
            mock_conn.wait_closed.assert_called_once()
            assert connector._connection is None

    @pytest.mark.asyncio
    async def test_context_manager_disconnects_on_exception(self) -> None:
        connector = SSHConnector(host="127.0.0.1", known_hosts=None)
        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        connect_path = "app.core.connectors.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            with pytest.raises(ValueError):
                async with connector:
                    raise ValueError("boom")
            mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_auth_when_no_credentials(self) -> None:
        connector = SSHConnector(host="127.0.0.1", known_hosts=None)
        mock_conn = AsyncMock()
        connect_path = "app.core.connectors.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            await connector.connect()
            call_kwargs = mock_connect.call_args[1]
            assert "password" not in call_kwargs
            assert "client_keys" not in call_kwargs
