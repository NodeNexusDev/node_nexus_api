"""Base connector interface."""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Protocol


class BaseConnector(ABC):
    """Abstract base connector interface."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""

    @abstractmethod
    async def execute_command(self, command: str) -> tuple[str, str, int]:
        """Execute a command on the remote system.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """

    async def __aenter__(self) -> "BaseConnector":
        """Enter async context manager."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager."""
        await self.disconnect()


class ConnectorFactory(Protocol):
    """Factory protocol for creating connectors."""

    def create_ssh(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        ssh_key: str | None,
    ) -> BaseConnector:
        """Create an SSH connector with the given parameters."""
        ...
