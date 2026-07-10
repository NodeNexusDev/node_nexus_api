"""Unit tests for SSH connector edge cases."""

from unittest.mock import AsyncMock, patch

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
