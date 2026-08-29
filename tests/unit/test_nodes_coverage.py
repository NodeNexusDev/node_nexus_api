"""Extra coverage for nodes API and services."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.nodes import _node_response  # noqa
from app.application.dto.node_management import NodeCreateDTO, NodeUpdateDTO
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_management_service import NodeManagementService


@pytest.mark.asyncio
async def test_create_node_host_key_fetch_failed():
    reader = AsyncMock()
    writer = AsyncMock()
    cipher = MagicMock()
    cipher.encrypt = lambda x: x
    known = AsyncMock()
    known.ensure_host.side_effect = RuntimeError("fail")
    svc = NodeManagementService(
        reader=reader, writer=writer, credential_cipher=cipher, known_hosts=known
    )
    writer.create_node.return_value = MagicMock(id=uuid.uuid4(), name="n")
    # Need to mock _log etc, but service will call audit.warning
    dto = NodeCreateDTO(
        name="n",
        endpoint=NodeEndpoint(host="h", port=22),
        credentials=NodeCredentials(username="u"),
        tags=(),
    )
    # Mock writer to return a view
    mock_view = MagicMock(spec=NodeViewDTO)
    mock_view.id = uuid.uuid4()
    mock_view.name = "n"
    writer.create_node.return_value = mock_view
    result = await svc.create_node(dto)
    assert result == mock_view
    known.ensure_host.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_node_host_port_change_fetch_failed():
    node_id = uuid.uuid4()
    current = MagicMock()
    current.endpoint.host = "oldhost"
    current.endpoint.port = 22
    reader = AsyncMock()
    reader.get_node.return_value = current
    writer = AsyncMock()
    writer.update_node.return_value = current
    cipher = MagicMock()
    cipher.encrypt = lambda x: x
    known = AsyncMock()
    known.ensure_host.side_effect = RuntimeError("fail")
    svc = NodeManagementService(
        reader=reader, writer=writer, credential_cipher=cipher, known_hosts=known
    )
    # Change host only
    dto = NodeUpdateDTO(changes=(("host", "newhost"),))
    result = await svc.update_node(node_id, dto)
    assert result == current
    # Change port only
    dto2 = NodeUpdateDTO(changes=(("port", 2222),))
    reader.get_node.return_value = current
    await svc.update_node(node_id, dto2)
    # Change both
    dto3 = NodeUpdateDTO(changes=(("host", "h2"), ("port", 2222)))
    await svc.update_node(node_id, dto3)


@pytest.mark.asyncio
async def test_update_node_status_history():
    node_id = uuid.uuid4()
    reader = AsyncMock()
    reader.get_node.return_value = None
    writer = AsyncMock()
    mock_view = MagicMock(spec=NodeViewDTO)
    mock_view.id = node_id
    writer.update_node.return_value = mock_view
    cipher = MagicMock()
    cipher.encrypt = lambda x: x
    history = AsyncMock()
    svc = NodeManagementService(
        reader=reader,
        writer=writer,
        credential_cipher=cipher,
        status_history_writer=history,
    )
    dto = NodeUpdateDTO(changes=(("status", "active"),))
    result = await svc.update_node(node_id, dto)
    assert result == mock_view
    history.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_node_encrypt_empty():
    reader = AsyncMock()
    writer = AsyncMock()
    cipher = MagicMock()
    cipher.encrypt = lambda x: f"enc:{x}" if x else x
    svc = NodeManagementService(
        reader=reader, writer=writer, credential_cipher=cipher, known_hosts=None
    )
    mock_view = MagicMock(spec=NodeViewDTO)
    mock_view.id = uuid.uuid4()
    writer.create_node.return_value = mock_view
    dto = NodeCreateDTO(
        name="n",
        endpoint=NodeEndpoint(host="h", port=22),
        credentials=NodeCredentials(username="u", password="", ssh_key=""),
        tags=(),
    )
    result = await svc.create_node(dto)
    assert result == mock_view
