"""Tests for dependency injection."""

import pytest
from dishka import make_async_container

from app.di.providers import AppProvider
from app.repositories.node_repo import NodeRepository
from app.services.node_service import NodeService


def test_di_container_can_be_created():
    """Test that DI container can be created."""
    container = make_async_container(AppProvider())
    assert container is not None
