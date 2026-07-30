"""SSH connector implementation."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

import asyncssh
import structlog

from app.application.command_policy import command_fingerprint
from app.core.connectors.base import BaseConnector, StreamEvent
from app.core.exceptions import ConnectionFailedError

logger = structlog.get_logger()  # operational: flow, performance
audit = structlog.get_logger("audit")  # security: access, commands, failures
_ALLOWED_SIGNALS = frozenset({"SIGINT", "SIGTERM", "SIGHUP"})
_STREAM_QUEUE_SIZE = 128


class SSHConnector(BaseConnector):
    """SSH connector for remote command execution."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        ssh_key: str | None = None,
        timeout: int = 30,
        known_hosts: str | None = None,
        strict_host_key_checking: bool = True,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._ssh_key = ssh_key
        self._timeout = timeout
        self._known_hosts = known_hosts
        self._strict_host_key_checking = strict_host_key_checking
        self._connection: asyncssh.SSHClientConnection | None = None
        self._active_process: Any | None = None

    async def connect(self) -> None:
        """Establish SSH connection.

        Key-based auth is used when ssh_key is provided.
        Password auth is used otherwise.
        """
        logger.debug("ssh.connect.start", host=self._host, port=self._port)
        if self._strict_host_key_checking and (
            not self._known_hosts or not Path(self._known_hosts).is_file()
        ):
            audit.warning(
                "ssh.host_key.configuration_invalid",
                host=self._host,
                port=self._port,
            )
            raise ConnectionFailedError("SSH host verification is unavailable")

        kwargs: dict[str, object] = {
            "port": self._port,
            "username": self._username,
            "connect_timeout": self._timeout,
            "known_hosts": self._known_hosts,
        }

        if self._ssh_key:
            kwargs["client_keys"] = [self._ssh_key.encode()]
        elif self._password:
            kwargs["password"] = self._password

        try:
            self._connection = await asyncssh.connect(self._host, **kwargs)
            audit.info("ssh.connect.ok", host=self._host, port=self._port)
        except asyncssh.Error as exc:
            audit.warning(
                "ssh.connect.failed",
                host=self._host,
                port=self._port,
                error_type=type(exc).__name__,
            )
            raise ConnectionFailedError("SSH connection failed") from exc

    async def disconnect(self) -> None:
        """Close SSH connection."""
        if self._connection:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None
            logger.debug("ssh.disconnect", host=self._host)

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        """Execute a command on the remote system.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        if not self._connection:
            raise RuntimeError("Not connected")

        fingerprint = command_fingerprint(command)
        logger.debug(
            "ssh.command.start",
            host=self._host,
            command_length=len(command),
            command_fingerprint=fingerprint,
        )
        try:
            result = await self._connection.run(command, timeout=self._timeout)
            exit_code = result.exit_status or 0
            audit.info(
                "ssh.command.ok",
                host=self._host,
                command_length=len(command),
                command_fingerprint=fingerprint,
                exit_code=exit_code,
                stdout_length=len(str(result.stdout)),
                stderr_length=len(str(result.stderr)),
            )
            return (
                str(result.stdout),
                str(result.stderr),
                exit_code,
            )
        except asyncssh.Error as exc:
            audit.error(
                "ssh.command.failed",
                host=self._host,
                command_length=len(command),
                command_fingerprint=fingerprint,
                error_type=type(exc).__name__,
            )
            raise ConnectionFailedError("SSH command failed") from exc

    async def execute_command_streaming(self, command: str) -> AsyncIterator[str]:
        """Execute a command and yield stdout chunks as they arrive.

        Yields lines of stdout output. Raises on connection errors.
        """
        if not self._connection:
            raise RuntimeError("Not connected")

        fingerprint = command_fingerprint(command)
        logger.debug(
            "ssh.stream.start",
            host=self._host,
            command_length=len(command),
            command_fingerprint=fingerprint,
        )
        try:
            async with self._connection.create_process(command) as process:
                async for line in process.stdout:
                    yield line
                # Wait for process to finish
                await process.wait()
                exit_code = process.exit_status or 0
                audit.info(
                    "ssh.stream.ok",
                    host=self._host,
                    command_length=len(command),
                    command_fingerprint=fingerprint,
                    exit_code=exit_code,
                )
        except asyncssh.Error as exc:
            audit.error(
                "ssh.stream.failed",
                host=self._host,
                command_length=len(command),
                command_fingerprint=fingerprint,
                error_type=type(exc).__name__,
            )
            raise ConnectionFailedError("SSH streaming command failed") from exc

    async def execute_command_streaming_events(
        self, command: str
    ) -> AsyncIterator[StreamEvent]:
        """Stream stdout/stderr separately and finish with the real exit status."""
        if not self._connection:
            raise RuntimeError("Not connected")
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue(_STREAM_QUEUE_SIZE)
        process = await self._connection.create_process(command)
        self._active_process = process

        async def pump(stream: Any, event_type: Literal["stdout", "stderr"]) -> None:
            async for chunk in stream:
                await queue.put(StreamEvent(type=event_type, data=str(chunk)))

        async def wait_for_exit() -> None:
            await process.wait()
            await queue.put(
                StreamEvent(type="exit", exit_code=process.exit_status or 0)
            )

        tasks = [
            asyncio.create_task(pump(process.stdout, "stdout")),
            asyncio.create_task(pump(process.stderr, "stderr")),
            asyncio.create_task(wait_for_exit()),
        ]
        try:
            while True:
                event = await queue.get()
                yield event
                if event.type == "exit":
                    break
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if getattr(process, "exit_status", None) is None:
                process.terminate()
            self._active_process = None

    async def send_signal(self, signal: str) -> None:
        """Send an allowlisted signal to the active SSH process."""
        if signal not in _ALLOWED_SIGNALS:
            raise ValueError("Signal is not allowed")
        if self._active_process is None:
            raise RuntimeError("No active process")
        self._active_process.send_signal(signal)


class SSHConnectorFactory:
    """Factory for creating SSH connectors."""

    def __init__(
        self,
        *,
        known_hosts_path: str = "/app/.ssh/known_hosts",
        strict_host_key_checking: bool = True,
    ) -> None:
        self._known_hosts_path = known_hosts_path
        self._strict_host_key_checking = strict_host_key_checking

    def create_ssh(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        ssh_key: str | None,
    ) -> SSHConnector:
        return SSHConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            ssh_key=ssh_key,
            known_hosts=(
                self._known_hosts_path if self._strict_host_key_checking else None
            ),
            strict_host_key_checking=self._strict_host_key_checking,
        )
