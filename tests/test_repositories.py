"""Tests for repository interfaces."""

from app.repositories.base import IRepository


def test_repository_interface_has_required_methods():
    """Test that IRepository defines required abstract methods."""
    assert hasattr(IRepository, "get_by_id")
    assert hasattr(IRepository, "get_all")
    assert hasattr(IRepository, "create")
    assert hasattr(IRepository, "update")
    assert hasattr(IRepository, "delete")
