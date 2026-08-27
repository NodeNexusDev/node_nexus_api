"""AsyncSSH outbound adapter."""

import asyncio
import shlex
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Self
from uuid import uuid4

import asyncssh
import structlog

from app.application.command_policy import command_fingerprint
from app.application.dto.remote_stream import RemoteStreamEventDTO
from app.core.exceptions import ConnectionFailedError

logger = structlog.get_logger()  # operational: flow, performance
audit = structlog.get_logger("audit")  # security: access, commands, failures
_ALLOWED_SIGNALS = frozenset({"SIGINT", "SIGTERM", "SIGHUP"})
_STREAM_QUEUE_SIZE = 128
_PROCESS_TERMINATION_TIMEOUT = 5.0
_MAX_CAPTURED_OUTPUT_BYTES = 1_048_576
_OUTPUT_TRUNCATED_MARKER = "\n...[remote output truncated]"


async def _read_bounded_stream(stream: Any, max_bytes: int) -> str:
    """Drain an SSH stream while retaining at most ``max_bytes`` in memory."""
    captured = bytearray()
    truncated = False
    async for chunk in stream:
        encoded = str(chunk).encode("utf-8")
        remaining = max_bytes - len(captured)
        if remaining > 0:
            captured.extend(encoded[:remaining])
        if len(encoded) > remaining:
            truncated = True
    value = captured.decode("utf-8", errors="replace")
    return value + _OUTPUT_TRUNCATED_MARKER if truncated else value


class SSHConnector:
    """SSH connector for remote command execution."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        ssh_key: str | None = None,
        passphrase: str | None = None,
        timeout: int = 30,
        known_hosts: str | None = None,
        strict_host_key_checking: bool = True,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._ssh_key = ssh_key
        self._passphrase = passphrase
        self._timeout = timeout
        self._known_hosts = known_hosts
        self._strict_host_key_checking = strict_host_key_checking
        self._connection: asyncssh.SSHClientConnection | None = None
        self._active_process: Any | None = None
        self._active_process_group_file: str | None = None

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
            if self._passphrase:
                kwargs["passphrase"] = self._passphrase
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

    async def __aenter__(self) -> Self:
        """Connect and enter the remote session."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Disconnect when leaving the remote session."""
        await self.disconnect()

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
            async with asyncio.timeout(self._timeout):
                async with self._connection.create_process(command) as process:
                    async with asyncio.TaskGroup() as tasks:
                        stdout_task = tasks.create_task(
                            _read_bounded_stream(
                                process.stdout,
                                _MAX_CAPTURED_OUTPUT_BYTES,
                            )
                        )
                        stderr_task = tasks.create_task(
                            _read_bounded_stream(
                                process.stderr,
                                _MAX_CAPTURED_OUTPUT_BYTES,
                            )
                        )
                        await process.wait()
                    stdout = stdout_task.result()
                    stderr = stderr_task.result()
                    exit_code = process.exit_status or 0
            audit.info(
                "ssh.command.ok",
                host=self._host,
                command_length=len(command),
                command_fingerprint=fingerprint,
                exit_code=exit_code,
                stdout_length=len(stdout),
                stderr_length=len(stderr),
            )
            return stdout, stderr, exit_code
        except (asyncssh.Error, TimeoutError) as exc:
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
                    yield str(line)
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
    ) -> AsyncGenerator[RemoteStreamEventDTO]:
        """Stream stdout/stderr separately and finish with the real exit status."""
        if not self._connection:
            raise RuntimeError("Not connected")
        queue: asyncio.Queue[RemoteStreamEventDTO] = asyncio.Queue(_STREAM_QUEUE_SIZE)
        group_file = f"{tempfile.gettempdir()}/node-nexus-stream-{uuid4().hex}.pid"
        grouped_command = f"printf '%s' \"$$\" > {group_file}; {command}"
        remote_command = (
            f'setsid sh -c {shlex.quote(grouped_command)}; status=$?; exit "$status"'
        )
        process = await self._connection.create_process(remote_command)
        self._active_process = process
        self._active_process_group_file = group_file

        async def pump(stream: Any, event_type: Literal["stdout", "stderr"]) -> None:
            async for chunk in stream:
                await queue.put(RemoteStreamEventDTO(type=event_type, data=str(chunk)))

        async def wait_for_exit() -> None:
            await process.wait()
            await queue.put(
                RemoteStreamEventDTO(
                    type="exit",
                    exit_code=process.exit_status or 0,
                )
            )

        pump_tasks = [
            asyncio.create_task(pump(process.stdout, "stdout")),
            asyncio.create_task(pump(process.stderr, "stderr")),
        ]
        exit_task = asyncio.create_task(wait_for_exit())
        try:
            while True:
                event = await queue.get()
                yield event
                if event.type == "exit":
                    break
        finally:
            for task in pump_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pump_tasks, return_exceptions=True)
            try:
                if getattr(process, "exit_status", None) is None:
                    await self._signal_active_process_group("TERM")
                try:
                    await asyncio.wait_for(
                        exit_task,
                        timeout=_PROCESS_TERMINATION_TIMEOUT,
                    )
                except TimeoutError:
                    await self._signal_active_process_group("KILL")
                    await process.wait()
            finally:
                if not exit_task.done():
                    exit_task.cancel()
                    await asyncio.gather(exit_task, return_exceptions=True)
                self._active_process = None
                await self._connection.run(
                    f"rm -f {group_file}",
                    check=False,
                )
                self._active_process_group_file = None

    async def send_signal(self, signal: str) -> None:
        """Send an allowlisted signal to the active SSH process."""
        if signal not in _ALLOWED_SIGNALS:
            raise ValueError("Signal is not allowed")
        if self._active_process is None:
            raise RuntimeError("No active process")
        # RFC 4254 uses signal names without the POSIX ``SIG`` prefix.
        await self._signal_active_process_group(signal.removeprefix("SIG"))

    async def abort_active_process(self) -> None:
        """Forcibly stop the active remote process group."""
        if self._active_process is not None:
            await self._signal_active_process_group("KILL")

    async def _signal_active_process_group(self, signal: str) -> None:
        """Signal the full remote process group, including command children."""
        if not self._connection or not self._active_process_group_file:
            raise RuntimeError("No active process")
        await self._connection.run(
            f"kill -{signal} -$(cat {self._active_process_group_file})",
            check=False,
        )


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
        passphrase: str | None = None,
    ) -> SSHConnector:
        return SSHConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            ssh_key=ssh_key,
            passphrase=passphrase,
            known_hosts=(
                self._known_hosts_path if self._strict_host_key_checking else None
            ),
            strict_host_key_checking=self._strict_host_key_checking,
        )
