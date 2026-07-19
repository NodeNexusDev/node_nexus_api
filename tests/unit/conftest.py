"""Shared test fixtures for unit tests."""

from typing import Any
from unittest.mock import MagicMock


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


class MockSessionContext:
    """Mock async context manager."""

    def __init__(self, return_value: Any) -> None:
        self._return_value = return_value

    async def __aenter__(self) -> Any:
        return self._return_value

    async def __aexit__(self, *args: Any) -> None:
        pass


class MockSession:
    """Mock session for auth dependency."""

    def __init__(self) -> None:
        pass

    async def execute(self, *args: Any) -> MagicMock:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    async def flush(self) -> None:
        pass

    def begin(self) -> MockSessionContext:
        return MockSessionContext(self)


class MockSessionmaker:
    """Mock sessionmaker for auth dependency."""

    def __call__(self) -> MockSessionContext:
        return MockSessionContext(MockSession())


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
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeResponse(**defaults)


def setup_test_app_auth(app: Any) -> None:
    """Set up auth mocks on a test app."""
    app.state.sessionmaker = MockSessionmaker()
