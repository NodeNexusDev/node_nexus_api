"""Unit tests for SSH connector edge cases."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.runtime.ssh import (
    SSHConnector,
    SSHConnectorFactory,
)
from app.application.command_policy import command_fingerprint
from app.core.exceptions import ConnectionFailedError


class AsyncChunks:
    def __init__(self, *chunks: str):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


def _command_context(
    stdout: tuple[str, ...],
    stderr: tuple[str, ...],
    exit_status: int | None,
) -> AsyncMock:
    process = AsyncMock()
    process.stdout = AsyncChunks(*stdout)
    process.stderr = AsyncChunks(*stderr)
    process.exit_status = exit_status
    process.wait = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = process
    return context


class TestSSHConnector:
    async def test_not_connected_raises(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        with pytest.raises(RuntimeError, match="Not connected"):
            await connector.execute_command("echo hi")

    async def test_disconnect_without_connection(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        await connector.disconnect()
        assert connector._connection is None

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

    async def test_key_auth_branch(self) -> None:
        key = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        connector = SSHConnector(
            host="127.0.0.1",
            ssh_key=key,
            known_hosts=None,
            strict_host_key_checking=False,
        )
        mock_conn = AsyncMock()
        connect_path = "app.adapters.runtime.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            await connector.connect()
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args
            assert "client_keys" in call_kwargs[1]
            assert connector._connection is mock_conn

    async def test_key_auth_with_passphrase(self) -> None:
        key = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        connector = SSHConnector(
            host="127.0.0.1",
            ssh_key=key,
            passphrase="secret-passphrase",
            known_hosts=None,
            strict_host_key_checking=False,
        )
        mock_conn = AsyncMock()
        connect_path = "app.adapters.runtime.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            await connector.connect()
            call_kwargs = mock_connect.call_args
            assert "client_keys" in call_kwargs[1]
            assert call_kwargs[1]["passphrase"] == "secret-passphrase"

    async def test_password_auth_branch(self) -> None:
        connector = SSHConnector(
            host="127.0.0.1",
            password="secret",
            known_hosts=None,
            strict_host_key_checking=False,
        )
        mock_conn = AsyncMock()
        connect_path = "app.adapters.runtime.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            await connector.connect()
            call_kwargs = mock_connect.call_args
            assert "password" in call_kwargs[1]
            assert call_kwargs[1]["password"] == "secret"

    async def test_execute_command_returns_tuple(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        mock_conn = MagicMock()
        mock_conn.create_process.return_value = _command_context(("output",), (), 0)
        connector._connection = mock_conn

        stdout, stderr, exit_code = await connector.execute_command("echo hi")
        assert stdout == "output"
        assert stderr == ""
        assert exit_code == 0

    async def test_execute_command_non_zero_exit(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        mock_conn = MagicMock()
        mock_conn.create_process.return_value = _command_context(
            (), ("command not found",), 127
        )
        connector._connection = mock_conn

        stdout, stderr, exit_code = await connector.execute_command("bad-cmd")
        assert exit_code == 127
        assert "not found" in stderr

    async def test_context_manager_calls_connect_disconnect(self) -> None:
        connector = SSHConnector(
            host="127.0.0.1",
            known_hosts=None,
            strict_host_key_checking=False,
        )
        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        connect_path = "app.adapters.runtime.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            async with connector:
                assert connector._connection is mock_conn
            mock_conn.close.assert_called_once()
            mock_conn.wait_closed.assert_called_once()
            assert connector._connection is None

    async def test_context_manager_disconnects_on_exception(self) -> None:
        connector = SSHConnector(
            host="127.0.0.1",
            known_hosts=None,
            strict_host_key_checking=False,
        )
        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        connect_path = "app.adapters.runtime.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            with pytest.raises(ValueError):
                async with connector:
                    raise ValueError("boom")
            mock_conn.close.assert_called_once()

    async def test_no_auth_when_no_credentials(self) -> None:
        connector = SSHConnector(
            host="127.0.0.1",
            known_hosts=None,
            strict_host_key_checking=False,
        )
        mock_conn = AsyncMock()
        connect_path = "app.adapters.runtime.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_conn
            await connector.connect()
            call_kwargs = mock_connect.call_args[1]
            assert "password" not in call_kwargs
            assert "client_keys" not in call_kwargs

    async def test_connect_error(self) -> None:
        import asyncssh

        connector = SSHConnector(
            host="127.0.0.1",
            known_hosts=None,
            strict_host_key_checking=False,
        )
        connect_path = "app.adapters.runtime.ssh.asyncssh.connect"
        with patch(connect_path, new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = asyncssh.Error("Connection refused", "")
            with pytest.raises(ConnectionFailedError):
                await connector.connect()

    async def test_execute_command_error(self) -> None:
        import asyncssh

        connector = SSHConnector(host="127.0.0.1")
        mock_conn = MagicMock()
        mock_conn.create_process.side_effect = asyncssh.Error("Channel closed", "")
        connector._connection = mock_conn

        with pytest.raises(ConnectionFailedError):
            await connector.execute_command("echo hi")

    async def test_execute_command_exit_status_none(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        mock_conn = MagicMock()
        mock_conn.create_process.return_value = _command_context(("output",), (), None)
        connector._connection = mock_conn

        stdout, stderr, exit_code = await connector.execute_command("echo hi")
        assert exit_code == 0

    async def test_execute_command_bounds_each_output_stream(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        mock_conn = MagicMock()
        mock_conn.create_process.return_value = _command_context(
            ("abcdef", "ghijkl"),
            ("123456",),
            0,
        )
        connector._connection = mock_conn

        with patch("app.adapters.runtime.ssh._MAX_CAPTURED_OUTPUT_BYTES", 8):
            stdout, stderr, _ = await connector.execute_command("large-output")

        assert stdout == "abcdefgh\n...[remote output truncated]"
        assert stderr == "123456"

    async def test_legacy_streaming_yields_stdout(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        process = AsyncMock()
        process.stdout = AsyncChunks("one", "two")
        process.exit_status = 3
        context = AsyncMock()
        context.__aenter__.return_value = process
        connection = MagicMock()
        connection.create_process.return_value = context
        connector._connection = connection

        assert [
            chunk async for chunk in connector.execute_command_streaming("run")
        ] == ["one", "two"]
        process.wait.assert_awaited_once()

    async def test_legacy_streaming_requires_connection(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        with pytest.raises(RuntimeError, match="Not connected"):
            await anext(connector.execute_command_streaming("run"))

    async def test_legacy_streaming_maps_ssh_error(self) -> None:
        import asyncssh

        connector = SSHConnector(host="127.0.0.1")
        context = AsyncMock()
        context.__aenter__.side_effect = asyncssh.Error("closed", "")
        connection = MagicMock()
        connection.create_process.return_value = context
        connector._connection = connection
        with pytest.raises(ConnectionFailedError):
            await anext(connector.execute_command_streaming("run"))

    async def test_typed_streaming_emits_both_streams_and_exit(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        process = AsyncMock()
        process.stdout = AsyncChunks("out")
        process.stderr = AsyncChunks("err")
        process.exit_status = 7
        connection = AsyncMock()
        connection.create_process.return_value = process
        connector._connection = connection

        events = [
            event async for event in connector.execute_command_streaming_events("run")
        ]
        assert {(event.type, event.data) for event in events[:-1]} == {
            ("stdout", "out"),
            ("stderr", "err"),
        }
        assert events[-1].type == "exit"
        assert events[-1].exit_code == 7
        assert connector._active_process is None

    async def test_typed_streaming_cleanup_terminates_unfinished_process(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        process = AsyncMock()
        process.stdout = AsyncChunks("out")
        process.stderr = AsyncChunks()
        process.exit_status = None
        terminated = asyncio.Event()
        process.wait.side_effect = terminated.wait
        connection = AsyncMock()
        connection.create_process.return_value = process

        async def complete_on_signal(command: str, *, check: bool) -> None:
            if command.startswith("kill -TERM"):
                terminated.set()

        connection.run.side_effect = complete_on_signal
        connector._connection = connection

        stream = connector.execute_command_streaming_events("run")
        await anext(stream)
        await stream.aclose()
        process.wait.assert_awaited_once()
        assert connection.run.await_count == 2

    async def test_typed_streaming_requires_connection(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        with pytest.raises(RuntimeError, match="Not connected"):
            await anext(connector.execute_command_streaming_events("run"))

    async def test_send_signal_validation_and_delivery(self) -> None:
        connector = SSHConnector(host="127.0.0.1")
        with pytest.raises(ValueError, match="not allowed"):
            await connector.send_signal("SIGKILL")
        with pytest.raises(RuntimeError, match="No active"):
            await connector.send_signal("SIGTERM")
        process = MagicMock()
        connector._active_process = process
        connector._active_process_group_file = "/tmp/process.pid"
        connector._connection = AsyncMock()
        await connector.send_signal("SIGINT")
        connector._connection.run.assert_awaited_once_with(
            "kill -INT -$(cat /tmp/process.pid)",
            check=False,
        )


class TestSSHConnectorFactory:
    def test_create_ssh(self) -> None:
        factory = SSHConnectorFactory()
        connector = factory.create_ssh(
            host="127.0.0.1",
            port=22,
            username="user",
            password="pass",
            ssh_key=None,
        )
        assert isinstance(connector, SSHConnector)
        assert connector._host == "127.0.0.1"
        assert connector._port == 22
        assert connector._username == "user"
        assert connector._password == "pass"
        assert connector._ssh_key is None
        assert connector._passphrase is None
        assert connector._known_hosts == "/app/.ssh/known_hosts"
        assert connector._strict_host_key_checking is True

    def test_create_ssh_with_passphrase(self) -> None:
        factory = SSHConnectorFactory()
        connector = factory.create_ssh(
            host="127.0.0.1",
            port=22,
            username="user",
            password=None,
            ssh_key="fake-key",
            passphrase="my-passphrase",
        )
        assert connector._ssh_key == "fake-key"
        assert connector._passphrase == "my-passphrase"

    def test_explicitly_disabled_host_key_checking(self) -> None:
        factory = SSHConnectorFactory(strict_host_key_checking=False)
        connector = factory.create_ssh("host", 22, "user", None, None)
        assert connector._known_hosts is None
        assert connector._strict_host_key_checking is False


async def test_missing_known_hosts_fails_closed(tmp_path) -> None:
    connector = SSHConnector(
        host="127.0.0.1",
        known_hosts=str(tmp_path / "missing"),
    )
    with pytest.raises(ConnectionFailedError, match="verification"):
        await connector.connect()


def test_command_fingerprint_is_stable_and_non_plaintext() -> None:
    first = command_fingerprint("echo secret")
    assert first == command_fingerprint("echo secret")
    assert first != command_fingerprint("echo other")
    assert "secret" not in first
