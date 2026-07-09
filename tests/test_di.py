"""Tests for dependency injection."""

from dishka import make_async_container

from app.di.providers import AppProvider


def test_di_container_can_be_created():
    """Test that DI container can be created."""
    container = make_async_container(AppProvider())
    assert container is not None
