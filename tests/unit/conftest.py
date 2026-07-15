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


def setup_test_app_auth(app: Any) -> None:
    """Set up auth mocks on a test app."""
    app.state.sessionmaker = MockSessionmaker()
