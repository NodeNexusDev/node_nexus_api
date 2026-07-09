"""Tests for repository interfaces and implementations."""

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
