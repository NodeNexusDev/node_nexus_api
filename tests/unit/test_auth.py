"""Unit tests for auth dependency (get_current_api_key)."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.api_key import APIKeyModel


def _make_api_key_model(**overrides: Any) -> APIKeyModel:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "test-key",
        "key_hash": "abc123",
        "key_prefix": "nnk_abcd",
        "is_active": True,
        "created_at": datetime.now(UTC),
        "last_used_at": None,
    }
    defaults.update(overrides)
    return APIKeyModel(**defaults)


def _create_app_with_auth() -> FastAPI:
    import fastapi

    from app.api.deps import get_current_api_key

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(
        _key: str = fastapi.Security(get_current_api_key),
    ) -> dict[str, str]:
        return {"key": _key}

    return app


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


class MockSessionContext:
    """Mock async context manager for session and session.begin()."""

    def __init__(self, return_value: Any) -> None:
        self._return_value = return_value

    async def __aenter__(self) -> Any:
        return self._return_value

    async def __aexit__(self, *args: Any) -> None:
        pass


class MockSession:
    """Mock session with begin() returning async context manager."""

    def __init__(self, execute_result: Any) -> None:
        self._execute_result = execute_result

    async def execute(self, *args: Any) -> MagicMock:
        # Use MagicMock for result so scalar_one_or_none() returns value directly
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self._execute_result
        return mock_result

    async def flush(self) -> None:
        pass

    def begin(self) -> MockSessionContext:
        return MockSessionContext(self)


class MockSessionmaker:
    """Mock sessionmaker that returns async context managers."""

    def __init__(self, execute_result: Any) -> None:
        self._execute_result = execute_result

    def __call__(self) -> MockSessionContext:
        return MockSessionContext(MockSession(self._execute_result))


def _make_mock_sessionmaker(model: Any = None) -> MockSessionmaker:
    return MockSessionmaker(execute_result=model)


class TestAuthMissingHeader:
    def test_returns_401(self) -> None:
        app = _create_app_with_auth()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")
        assert response.status_code == 401
        assert "Missing X-API-Key header" in response.json()["detail"]


class TestAuthMasterKey:
    @patch("app.api.deps.get_settings")
    def test_master_key_returns_master(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-123")

        app = _create_app_with_auth()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "test-master-123"})
        assert response.status_code == 200
        assert response.json()["key"] == "master"

    @patch("app.api.deps.get_settings")
    def test_empty_master_key_skips_check(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        app = _create_app_with_auth()
        app.state.sessionmaker = _make_mock_sessionmaker(model=None)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "some-key"})
        assert response.status_code == 401


class TestAuthInvalidKey:
    @patch("app.api.deps.get_settings")
    def test_invalid_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        app = _create_app_with_auth()
        app.state.sessionmaker = _make_mock_sessionmaker(model=None)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "nnk_invalidkey123"})
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]


class TestAuthRevokedKey:
    @patch("app.api.deps.get_settings")
    def test_revoked_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        app = _create_app_with_auth()
        revoked_model = _make_api_key_model(is_active=False)
        app.state.sessionmaker = _make_mock_sessionmaker(model=revoked_model)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "nnk_revokedkey1"})
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()


class TestAuthValidKey:
    @patch("app.api.deps.get_settings")
    def test_valid_key_returns_prefix(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        app = _create_app_with_auth()
        active_model = _make_api_key_model()
        app.state.sessionmaker = _make_mock_sessionmaker(model=active_model)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "nnk_validkey123456"})
        assert response.status_code == 200
        assert response.json()["key"] == "nnk_validkey"
