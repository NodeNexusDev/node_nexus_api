"""Shared test fixtures for unit tests."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from dishka import Provider, Scope, provide

from app.services.api_key_service import APIKeyService


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


class MockAuthServiceProvider(Provider):
    """Provider that returns a mock APIKeyService for auth tests."""

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(self) -> APIKeyService:
        mock = AsyncMock(spec=APIKeyService)
        mock.validate_api_key.return_value = None
        return mock


def make_orm_node(**overrides: Any) -> Any:
    """Create a NodeModel with defaults for testing."""
    import uuid
    from datetime import UTC, datetime

    from app.models.node import NodeModel

    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "server-1",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "password": None,
        "ssh_key": None,
        "docker_host": None,
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


def make_orm_command(**overrides: Any) -> Any:
    """Create a CommandModel with defaults for testing."""
    import uuid
    from datetime import UTC, datetime

    from app.models.command import CommandModel

    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "check_disk",
        "description": "Check disk usage",
        "command": "df -h",
        "parameters": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return CommandModel(**defaults)


def make_response(**overrides: Any) -> Any:
    """Create a NodeResponse with defaults for testing."""
    import uuid
    from datetime import UTC, datetime

    from app.schemas.node import NodeResponse

    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "server-1",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "docker_host": None,
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeResponse(**defaults)
