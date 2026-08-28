"""Tests for transport-independent streaming command orchestration."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.streaming_command_service import StreamingCommandService
from app.core.exceptions import NodeNotFoundError


async def test_connect_resolves_dto_and_always_disconnects() -> None:
    node_id = uuid4()
    reader = AsyncMock()
    reader.get_connection.return_value = NodeConnectionDTO(
        id=node_id,
        name="node",
        endpoint=NodeEndpoint(host="host", port=22, connection_type="ssh"),
        credentials=NodeCredentials(username="root"),
    )
    connector = AsyncMock()
    factory = MagicMock()
    factory.create_ssh.return_value = connector
    cipher = MagicMock()
    cipher.decrypt.side_effect = lambda value: value
    service = StreamingCommandService(reader, factory, cipher)

    with pytest.raises(RuntimeError, match="cancelled"):
        async with service.connect(node_id):
            connector.connect.assert_awaited_once()
            raise RuntimeError("cancelled")

    connector.disconnect.assert_awaited_once()


async def test_connect_rejects_unknown_node_before_connector_creation() -> None:
    reader = AsyncMock()
    reader.get_connection.return_value = None
    factory = MagicMock()
    service = StreamingCommandService(reader, factory, MagicMock())

    with pytest.raises(NodeNotFoundError):
        async with service.connect(uuid4()):
            pytest.fail("unknown node must not open a session")

    factory.create_ssh.assert_not_called()
