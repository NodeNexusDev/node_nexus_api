"""Tests for services."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NodeNotFoundError
from app.schemas.node import NodeCreate, NodeUpdate
from app.services.node_service import NodeService


@pytest.fixture
def mock_repository():
    """Create a mock node repository."""
    return AsyncMock()


@pytest.fixture
def node_service(mock_repository):
    """Create a NodeService with mock repository."""
    return NodeService(repository=mock_repository)


def _make_mock_node(
    node_id: uuid.UUID | None = None,
    name: str = "test",
    host: str = "192.168.1.100",
    port: int = 22,
    connection_type: str = "ssh",
    status: str = "active",
    username: str | None = "testuser",
) -> MagicMock:
    """Create a mock node object."""
    mock_node = MagicMock()
    mock_node.id = node_id or uuid.uuid4()
    mock_node.name = name
    mock_node.host = host
    mock_node.port = port
    mock_node.connection_type = connection_type
    mock_node.status = status
    mock_node.username = username
    mock_node.created_at = datetime.now(UTC)
    mock_node.updated_at = datetime.now(UTC)
    return mock_node


async def test_get_node_found(node_service, mock_repository):
    """Test getting an existing node."""
    node_id = uuid.uuid4()
    mock_repository.get_by_id.return_value = _make_mock_node(node_id=node_id)

    result = await node_service.get_node(node_id)

    assert result.id == node_id
    mock_repository.get_by_id.assert_called_once_with(node_id)


async def test_get_node_not_found(node_service, mock_repository):
    """Test getting a non-existent node raises exception."""
    node_id = uuid.uuid4()
    mock_repository.get_by_id.return_value = None

    with pytest.raises(NodeNotFoundError):
        await node_service.get_node(node_id)


async def test_get_all_nodes(node_service, mock_repository):
    """Test getting all nodes."""
    mock_nodes = [_make_mock_node(), _make_mock_node()]
    mock_repository.get_all.return_value = mock_nodes

    result = await node_service.get_all_nodes()

    assert len(result) == 2
    mock_repository.get_all.assert_called_once_with(skip=0, limit=100)


async def test_get_all_nodes_with_pagination(node_service, mock_repository):
    """Test getting all nodes with pagination."""
    mock_repository.get_all.return_value = []

    await node_service.get_all_nodes(skip=10, limit=5)

    mock_repository.get_all.assert_called_once_with(skip=10, limit=5)


async def test_create_node(node_service, mock_repository):
    """Test creating a new node."""
    mock_node = _make_mock_node()
    mock_repository.create.return_value = mock_node
    data = NodeCreate(name="test", host="192.168.1.100", connection_type="ssh")

    result = await node_service.create_node(data)

    assert result.name == "test"
    assert result.host == "192.168.1.100"
    mock_repository.create.assert_called_once()


async def test_update_node_found(node_service, mock_repository):
    """Test updating an existing node."""
    node_id = uuid.uuid4()
    mock_node = _make_mock_node(node_id=node_id, name="new-name")
    mock_repository.update.return_value = mock_node
    data = NodeUpdate(name="new-name")

    result = await node_service.update_node(node_id, data)

    assert result.name == "new-name"
    mock_repository.update.assert_called_once_with(node_id, {"name": "new-name"})


async def test_update_node_not_found(node_service, mock_repository):
    """Test updating a non-existent node raises exception."""
    node_id = uuid.uuid4()
    mock_repository.update.return_value = None
    data = NodeUpdate(name="new-name")

    with pytest.raises(NodeNotFoundError):
        await node_service.update_node(node_id, data)


async def test_delete_node_found(node_service, mock_repository):
    """Test deleting an existing node."""
    node_id = uuid.uuid4()
    mock_repository.delete.return_value = True

    result = await node_service.delete_node(node_id)

    assert result is True
    mock_repository.delete.assert_called_once_with(node_id)


async def test_delete_node_not_found(node_service, mock_repository):
    """Test deleting a non-existent node raises exception."""
    node_id = uuid.uuid4()
    mock_repository.delete.return_value = False

    with pytest.raises(NodeNotFoundError):
        await node_service.delete_node(node_id)
