"""Unit tests for auth dependency (get_current_api_key)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient, Response

from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
    AuthenticatedPrincipal,
)
from app.core.exceptions import (
    APIKeyRevokedError,
    AuthenticationError,
    DomainError,
)


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


def _principal(scope: str = "read-write") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        key_id=uuid4(),
        key_prefix="nnk_vali",
        scope=scope,
    )


async def _get(
    app: FastAPI,
    path: str,
    headers: dict[str, str] | None = None,
) -> Response:
    """Run one request without the blocking sync TestClient bridge."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        return await client.get(path, headers=headers)


def _create_app_with_auth(
    mock_service: APIKeyAuthenticationService | AsyncMock | None = None,
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
            AuthenticationError: 401,
            APIKeyRevokedError: 401,
        }
        status_code = _error_status_map.get(type(exc), 422)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    if mock_service is None:
        mock_service = AsyncMock(spec=APIKeyAuthenticationService)
        mock_service.authenticate.return_value = _principal()

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> APIKeyAuthenticationService:
            return mock_service

    container = make_async_container(MockServiceProvider())
    setup_dishka(container, app)

    return app


class TestAuthMissingHeader:
    async def test_returns_401(self) -> None:
        app = _create_app_with_auth()
        response = await _get(app, "/test")
        assert response.status_code == 401
        assert "Missing X-API-Key header" in response.json()["detail"]


class TestAuthMasterKey:
    @patch("app.api.deps.get_settings")
    async def test_master_key_returns_master(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-123")

        app = _create_app_with_auth()
        response = await _get(app, "/test", {"X-API-Key": "test-master-123"})
        assert response.status_code == 200
        assert response.json()["key"] == "master"

    @patch("app.api.deps.get_settings")
    async def test_empty_master_key_skips_check(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.authenticate.side_effect = AuthenticationError("Invalid API key")

        app = _create_app_with_auth(mock_service)
        response = await _get(app, "/test", {"X-API-Key": "some-key"})
        assert response.status_code == 401


class TestAuthInvalidKey:
    @patch("app.api.deps.get_settings")
    async def test_invalid_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.authenticate.side_effect = AuthenticationError("Invalid API key")

        app = _create_app_with_auth(mock_service)
        response = await _get(app, "/test", {"X-API-Key": "nnk_invalidkey123"})
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]


class TestAuthRevokedKey:
    @patch("app.api.deps.get_settings")
    async def test_revoked_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.authenticate.side_effect = APIKeyRevokedError(
            "API key has been revoked"
        )

        app = _create_app_with_auth(mock_service)
        response = await _get(app, "/test", {"X-API-Key": "nnk_revokedkey1"})
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()


class TestAuthValidKey:
    @patch("app.api.deps.get_settings")
    async def test_valid_key_returns_prefix(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.authenticate.return_value = _principal()

        app = _create_app_with_auth(mock_service)
        response = await _get(app, "/test", {"X-API-Key": "nnk_validkey123456"})
        assert response.status_code == 200
        assert response.json()["key"] == "nnk_vali"


# --- Scope enforcement tests ---


def _create_app_with_write_scope(
    mock_service: APIKeyAuthenticationService | AsyncMock | None = None,
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
            AuthenticationError: 401,
            APIKeyRevokedError: 401,
        }
        status_code = _error_status_map.get(type(exc), 422)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    if mock_service is None:
        mock_service = AsyncMock(spec=APIKeyAuthenticationService)
        mock_service.authenticate.return_value = _principal()

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> APIKeyAuthenticationService:
            return mock_service

    container = make_async_container(MockServiceProvider())
    setup_dishka(container, app)

    return app


class TestScopeEnforcement:
    @patch("app.api.deps.get_settings")
    async def test_master_key_has_write_scope(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-123")

        app = _create_app_with_write_scope()
        response = await _get(
            app,
            "/test-write",
            {"X-API-Key": "test-master-123"},
        )
        assert response.status_code == 200
        assert response.json()["key"] == "master"

    @patch("app.api.deps.get_settings")
    async def test_read_write_key_has_write_scope(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.authenticate.return_value = _principal()

        app = _create_app_with_write_scope(mock_service)
        response = await _get(
            app,
            "/test-write",
            {"X-API-Key": "nnk_validkey123"},
        )
        assert response.status_code == 200

    @patch("app.api.deps.get_settings")
    async def test_read_only_key_denied(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        mock_service = AsyncMock()
        mock_service.authenticate.return_value = _principal(scope="read-only")

        app = _create_app_with_write_scope(mock_service)
        response = await _get(
            app,
            "/test-write",
            {"X-API-Key": "nnk_readonly1"},
        )
        assert response.status_code == 403
        assert "read-only" in response.json()["detail"].lower()

    @patch("app.api.deps.get_settings")
    async def test_missing_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        app = _create_app_with_write_scope()
        response = await _get(app, "/test-write")
        assert response.status_code == 401
