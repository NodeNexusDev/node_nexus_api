"""Base connector interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One version-independent remote process stream event."""

    type: str
    data: str | None = None
    exit_code: int | None = None


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

    async def execute_command_streaming(self, command: str) -> AsyncIterator[str]:
        """Execute a command and stream stdout chunks.

        Not all connectors support streaming. Default raises NotImplementedError.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support command streaming"
        )
        # Make this an async generator for correct type narrowing
        # (ty infers async def without yield as Coroutine, not AsyncIterator)
        yield  # type: ignore[unreachable]

    async def execute_command_streaming_events(
        self, command: str
    ) -> AsyncIterator[StreamEvent]:
        """Stream typed events, with a compatibility fallback for connectors."""
        async for chunk in self.execute_command_streaming(command):
            yield StreamEvent(type="stdout", data=chunk)
        yield StreamEvent(type="exit", exit_code=0)

    async def send_signal(self, signal: str) -> None:
        """Send a signal to the active process when supported."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support process signals"
        )

    async def __aenter__(self) -> Self:
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
