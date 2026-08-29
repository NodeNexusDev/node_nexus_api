"""Tests for NodeHostKeyService."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.services.node_host_key_service import NodeHostKeyService
from app.core.exceptions import HostKeyFetchError, NodeNotFoundError


@pytest.mark.asyncio
async def test_refresh_host_key_success():
    node_id = uuid.uuid4()
    mock_node = AsyncMock()
    mock_node.endpoint.host = "example.com"
    mock_node.endpoint.port = 22
    reader = AsyncMock()
    reader.get_node.return_value = mock_node
    known = AsyncMock()
    known.refresh_host.return_value = True
    svc = NodeHostKeyService(reader, known)
    result = await svc.refresh_host_key(node_id)
    assert result == mock_node
    known.refresh_host.assert_awaited_once_with("example.com", 22)


@pytest.mark.asyncio
async def test_refresh_host_key_not_found():
    reader = AsyncMock()
    reader.get_node.return_value = None
    known = AsyncMock()
    svc = NodeHostKeyService(reader, known)
    with pytest.raises(NodeNotFoundError):
        await svc.refresh_host_key(uuid.uuid4())


@pytest.mark.asyncio
async def test_refresh_host_key_fetch_error_propagates():
    node_id = uuid.uuid4()
    mock_node = AsyncMock()
    mock_node.endpoint.host = "h"
    mock_node.endpoint.port = 2222
    reader = AsyncMock()
    reader.get_node.return_value = mock_node
    known = AsyncMock()
    known.refresh_host.side_effect = HostKeyFetchError("fail")
    svc = NodeHostKeyService(reader, known)
    with pytest.raises(HostKeyFetchError):
        await svc.refresh_host_key(node_id)


@pytest.mark.asyncio
async def test_refresh_host_key_generic_exception_wrapped():
    node_id = uuid.uuid4()
    mock_node = AsyncMock()
    mock_node.endpoint.host = "h"
    mock_node.endpoint.port = 22
    reader = AsyncMock()
    reader.get_node.return_value = mock_node
    known = AsyncMock()
    known.refresh_host.side_effect = RuntimeError("boom")
    svc = NodeHostKeyService(reader, known)
    with pytest.raises(HostKeyFetchError, match="Failed to refresh"):
        await svc.refresh_host_key(node_id)
