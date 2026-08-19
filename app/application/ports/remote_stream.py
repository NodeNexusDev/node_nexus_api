"""Remote process streaming ports."""

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Protocol

from app.application.dto.remote_stream import RemoteStreamEventDTO


class RemoteStreamingConnector(Protocol):
    """Connected remote session capable of process streaming and signaling."""

    async def connect(self) -> None:
        """Establish the remote connection."""
        ...

    async def disconnect(self) -> None:
        """Close the remote connection."""
        ...

    def execute_command_streaming(self, command: str) -> AsyncIterator[str]:
        """Stream stdout chunks for compatibility consumers."""
        ...

    def execute_command_streaming_events(
        self, command: str
    ) -> AsyncGenerator[RemoteStreamEventDTO]:
        """Stream typed stdout, stderr, and exit events."""
        ...

    async def send_signal(self, signal: str) -> None:
        """Forward an allowed signal to the active process."""
        ...

    async def abort_active_process(self) -> None:
        """Forcibly stop the active process group during cleanup."""
        ...


class RemoteStreamingConnectorFactory(Protocol):
    """Create streaming connectors without exposing a transport implementation."""

    def create_ssh(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        ssh_key: str | None,
        passphrase: str | None = None,
    ) -> RemoteStreamingConnector:
        """Create one SSH-backed streaming connector."""
        ...
