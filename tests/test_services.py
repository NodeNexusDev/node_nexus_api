"""Tests for services."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NodeNotFoundError
from app.services.node_service import NodeService


@pytest.fixture
def mock_repository():
    """Create a mock node repository."""
    return AsyncMock()


@pytest.fixture
def node_service(mock_repository):
    """Create a NodeService with mock repository."""
    return NodeService(repository=mock_repository)


async def test_get_node_found(node_service, mock_repository):
    """Test getting an existing node."""
    node_id = uuid.uuid4()
    mock_node = MagicMock()
    mock_node.id = node_id
    mock_node.name = "test"
    mock_node.host = "192.168.1.100"
    mock_node.port = 22
    mock_node.connection_type = "ssh"
    mock_node.status = "active"
    mock_node.created_at = datetime.now(UTC)
    mock_node.updated_at = datetime.now(UTC)
    mock_repository.get_by_id.return_value = mock_node

    result = await node_service.get_node(node_id)

    assert result["id"] == node_id
    mock_repository.get_by_id.assert_called_once_with(node_id)


async def test_get_node_not_found(node_service, mock_repository):
    """Test getting a non-existent node raises exception."""
    node_id = uuid.uuid4()
    mock_repository.get_by_id.return_value = None

    with pytest.raises(NodeNotFoundError):
        await node_service.get_node(node_id)
