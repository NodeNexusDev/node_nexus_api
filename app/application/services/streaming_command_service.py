"""Streaming command orchestration independent from the WebSocket adapter."""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.application.dto.remote_stream import RemoteStreamEventDTO
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.node_reader import NodeConnectionReader
from app.application.ports.remote_stream import (
    RemoteStreamingConnector,
    RemoteStreamingConnectorFactory,
)
from app.core.exceptions import NodeNotFoundError


class StreamingCommandSession:
    """Connected remote session used by a transport adapter."""

    def __init__(self, connector: RemoteStreamingConnector) -> None:
        self._connector = connector

    def execute(self, command: str) -> AsyncIterator[str]:
        """Stream command output."""
        return self._connector.execute_command_streaming(command)

    def execute_events(self, command: str) -> AsyncGenerator[RemoteStreamEventDTO]:
        """Stream typed stdout, stderr, and exit events."""
        return self._connector.execute_command_streaming_events(command)

    async def send_signal(self, signal: str) -> None:
        """Forward an allowed signal to the active remote process."""
        await self._connector.send_signal(signal)

    async def abort_active_process(self) -> None:
        """Forcibly stop the active remote process group."""
        await self._connector.abort_active_process()


class StreamingCommandService:
    """Open and safely finalize streaming command sessions."""

    def __init__(
        self,
        node_reader: NodeConnectionReader,
        connector_factory: RemoteStreamingConnectorFactory,
        credential_cipher: CredentialCipher,
    ) -> None:
        self._node_reader = node_reader
        self._connector_factory = connector_factory
        self._credential_cipher = credential_cipher

    @asynccontextmanager
    async def connect(self, node_id: UUID) -> AsyncIterator[StreamingCommandSession]:
        """Resolve credentials, connect, and guarantee connector cleanup."""
        node = await self._node_reader.get_connection(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        connector = self._connector_factory.create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=self._credential_cipher.decrypt(node.password),
            ssh_key=self._credential_cipher.decrypt(node.ssh_key),
            passphrase=self._credential_cipher.decrypt(node.passphrase),
        )
        await connector.connect()
        try:
            yield StreamingCommandSession(connector)
        finally:
            await connector.disconnect()
