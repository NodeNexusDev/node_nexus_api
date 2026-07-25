"""Unit tests for auth dependency (get_current_api_key)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    APIKeyNotFoundError,
    APIKeyRevokedError,
    DomainError,
)
from app.services.api_key_service import APIKeyService


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


def _create_app_with_auth(
    mock_service: APIKeyService | AsyncMock | None = None,
) -> FastAPI:
    import fastapi
    from fastapi.responses import JSONResponse

    from app.api.deps import get_current_api_key

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(
        _key: str = fastapi.Security(get_current_api_key),
    ) -> dict[str, str]:
        return {"key": _key}

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Any, exc: DomainError) -> JSONResponse:
        _error_status_map: dict[type[DomainError], int] = {
            APIKeyNotFoundError: 401,
            APIKeyRevokedError: 401,
        }
        status_code = _error_status_map.get(type(exc), 422)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    if mock_service is None:
        mock_service = AsyncMock(spec=APIKeyService)
        mock_service.validate_api_key.return_value = None

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> APIKeyService:
            return mock_service

    container = make_async_container(MockServiceProvider())
    setup_dishka(container, app)

    return app


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

        mock_service = AsyncMock()
        mock_service.validate_api_key.side_effect = APIKeyNotFoundError(
            "Invalid API key"
        )

        app = _create_app_with_auth(mock_service)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "some-key"})
        assert response.status_code == 401


class TestAuthInvalidKey:
    @patch("app.api.deps.get_settings")
    def test_invalid_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.validate_api_key.side_effect = APIKeyNotFoundError(
            "Invalid API key"
        )

        app = _create_app_with_auth(mock_service)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "nnk_invalidkey123"})
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]


class TestAuthRevokedKey:
    @patch("app.api.deps.get_settings")
    def test_revoked_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.validate_api_key.side_effect = APIKeyRevokedError(
            "API key has been revoked"
        )

        app = _create_app_with_auth(mock_service)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "nnk_revokedkey1"})
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()


class TestAuthValidKey:
    @patch("app.api.deps.get_settings")
    def test_valid_key_returns_prefix(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.validate_api_key.return_value = None

        app = _create_app_with_auth(mock_service)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test", headers={"X-API-Key": "nnk_validkey123456"})
        assert response.status_code == 200
        assert response.json()["key"] == "nnk_vali"


# --- Scope enforcement tests ---


def _create_app_with_write_scope(
    mock_service: APIKeyService | AsyncMock | None = None,
) -> FastAPI:
    """Create app with require_write_scope dependency."""
    import fastapi
    from fastapi.responses import JSONResponse

    from app.api.deps import require_write_scope

    app = FastAPI()

    @app.get("/test-write")
    async def test_write_endpoint(
        _key: str = fastapi.Security(require_write_scope),
    ) -> dict[str, str]:
        return {"key": _key}

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Any, exc: DomainError) -> JSONResponse:
        _error_status_map: dict[type[DomainError], int] = {
            APIKeyNotFoundError: 401,
            APIKeyRevokedError: 401,
        }
        status_code = _error_status_map.get(type(exc), 422)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    if mock_service is None:
        mock_service = AsyncMock(spec=APIKeyService)
        mock_service.validate_api_key.return_value = None
        mock_service.get_api_key_scope.return_value = "read-write"

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> APIKeyService:
            return mock_service

    container = make_async_container(MockServiceProvider())
    setup_dishka(container, app)

    return app


class TestScopeEnforcement:
    @patch("app.api.deps.get_settings")
    def test_master_key_has_write_scope(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-123")

        app = _create_app_with_write_scope()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-write", headers={"X-API-Key": "test-master-123"})
        assert response.status_code == 200
        assert response.json()["key"] == "master"

    @patch("app.api.deps.get_settings")
    def test_read_write_key_has_write_scope(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.validate_api_key.return_value = None
        mock_service.get_api_key_scope.return_value = "read-write"

        app = _create_app_with_write_scope(mock_service)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-write", headers={"X-API-Key": "nnk_validkey123"})
        assert response.status_code == 200

    @patch("app.api.deps.get_settings")
    def test_read_only_key_denied(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.validate_api_key.return_value = None
        mock_service.get_api_key_scope.return_value = "read-only"

        app = _create_app_with_write_scope(mock_service)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-write", headers={"X-API-Key": "nnk_readonly1"})
        assert response.status_code == 403
        assert "read-only" in response.json()["detail"].lower()

    @patch("app.api.deps.get_settings")
    def test_missing_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        app = _create_app_with_write_scope()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-write")
        assert response.status_code == 401
