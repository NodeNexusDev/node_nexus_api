"""Tests for repository interfaces and implementations."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.base import IRepository
from app.repositories.node_repo import NodeRepository


def test_repository_interface_has_required_methods():
    """Test that IRepository defines required abstract methods."""
    assert hasattr(IRepository, "get_by_id")
    assert hasattr(IRepository, "get_all")
    assert hasattr(IRepository, "create")
    assert hasattr(IRepository, "update")
    assert hasattr(IRepository, "delete")


def test_node_repository_inherits_from_base():
    """Test that NodeRepository implements IRepository."""
    assert issubclass(NodeRepository, IRepository)


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession with correct sync/async method types."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def node_repository(mock_session):
    """Create a NodeRepository with mock session."""
    return NodeRepository(session=mock_session)


async def test_get_by_id_found(node_repository, mock_session):
    """Test getting a node by ID when found."""
    node_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock(id=node_id)
    mock_session.execute.return_value = mock_result

    result = await node_repository.get_by_id(node_id)

    assert result is not None
    assert result.id == node_id


async def test_get_by_id_not_found(node_repository, mock_session):
    """Test getting a node by ID when not found."""
    node_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    result = await node_repository.get_by_id(node_id)

    assert result is None


async def test_get_all(node_repository, mock_session):
    """Test getting all nodes."""
    mock_node1 = MagicMock()
    mock_node2 = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_node1, mock_node2]
    mock_session.execute.return_value = mock_result

    result = await node_repository.get_all()

    assert len(result) == 2


async def test_get_all_with_pagination(node_repository, mock_session):
    """Test getting all nodes with pagination."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    await node_repository.get_all(skip=10, limit=5)

    mock_session.execute.assert_called_once()


async def test_create_node(node_repository, mock_session):
    """Test creating a new node."""
    data = {
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
    }

    result = await node_repository.create(data)

    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()
    assert result.name == "test-node"
    assert result.host == "192.168.1.100"


async def test_update_node_found(node_repository, mock_session):
    """Test updating an existing node."""
    node_id = uuid.uuid4()
    mock_node = MagicMock()
    mock_node.name = "old-name"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_node
    mock_session.execute.return_value = mock_result

    result = await node_repository.update(node_id, {"name": "new-name"})

    assert result is not None
    assert result.name == "new-name"
    mock_session.flush.assert_called_once()


async def test_update_node_not_found(node_repository, mock_session):
    """Test updating a non-existent node."""
    node_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    result = await node_repository.update(node_id, {"name": "new-name"})

    assert result is None
    mock_session.flush.assert_not_called()


async def test_delete_node_found(node_repository, mock_session):
    """Test deleting an existing node."""
    node_id = uuid.uuid4()
    mock_node = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_node
    mock_session.execute.return_value = mock_result

    result = await node_repository.delete(node_id)

    assert result is True
    mock_session.delete.assert_called_once_with(mock_node)
    mock_session.flush.assert_called_once()


async def test_delete_node_not_found(node_repository, mock_session):
    """Test deleting a non-existent node."""
    node_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    result = await node_repository.delete(node_id)

    assert result is False
    mock_session.delete.assert_not_called()
    mock_session.flush.assert_not_called()
