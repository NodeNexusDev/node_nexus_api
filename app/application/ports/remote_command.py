"""Remote command execution ports."""

from types import TracebackType
from typing import Protocol, Self


class RemoteCommandSession(Protocol):
    """Connected remote session capable of executing commands."""

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        """Execute one command and return stdout, stderr, and exit code."""
        ...

    async def __aenter__(self) -> Self:
        """Connect and enter the remote session."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the remote session."""
        ...


class RemoteConnectorFactory(Protocol):
    """Create remote command sessions without exposing an implementation."""

    def create_ssh(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        ssh_key: str | None,
        passphrase: str | None = None,
    ) -> RemoteCommandSession:
        """Create one SSH-backed remote command session."""
        ...
