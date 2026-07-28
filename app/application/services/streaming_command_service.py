"""Streaming command orchestration independent from the WebSocket adapter."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.application.ports.node_reader import NodeConnectionReader
from app.core.connectors.base import BaseConnector, ConnectorFactory
from app.core.exceptions import NodeNotFoundError
from app.core.ssh_utils import decrypt_value


class StreamingCommandSession:
    """Connected remote session used by a transport adapter."""

    def __init__(self, connector: BaseConnector) -> None:
        self._connector = connector

    def execute(self, command: str) -> AsyncIterator[str]:
        """Stream command output."""
        return self._connector.execute_command_streaming(command)


class StreamingCommandService:
    """Open and safely finalize streaming command sessions."""

    def __init__(
        self,
        node_reader: NodeConnectionReader,
        connector_factory: ConnectorFactory,
    ) -> None:
        self._node_reader = node_reader
        self._connector_factory = connector_factory

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
            password=decrypt_value(node.password),
            ssh_key=decrypt_value(node.ssh_key),
        )
        await connector.connect()
        try:
            yield StreamingCommandSession(connector)
        finally:
            await connector.disconnect()
