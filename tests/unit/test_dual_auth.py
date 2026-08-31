"""Tests for dual-auth dependencies."""

from importlib.metadata import PackageNotFoundError
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, HTTPException
from httpx2 import ASGITransport, AsyncClient, Response

from app.api.deps import Principal
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
    AuthenticatedPrincipal,
)
from app.core.exceptions import (
    AuthenticationError,
    DomainError,
)
from tests.typing import as_typed_mock


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


def _mock_jwt_handler(
    user_id: str | None = None,
    claims: dict[str, Any] | None = None,
) -> MagicMock:
    handler = MagicMock(spec=JWTHandler)
    if user_id is None:
        user_id = str(uuid4())
    if claims is None:
        claims = {"sub": user_id, "is_superuser": False, "type": "access"}
    handler.decode_token.return_value = claims
    return handler


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
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        return await client.get(path, headers=headers)


# --- get_current_principal tests ---


def _create_app_principal(
    mock_api_key_service: AsyncMock | None = None,
    mock_jwt: MagicMock | None = None,
) -> FastAPI:
    import fastapi
    from fastapi.responses import JSONResponse

    from app.api.deps import get_current_principal

    app = FastAPI()

    @app.get("/test-principal")
    async def test_endpoint(
        _p: Principal = fastapi.Security(get_current_principal),
    ) -> dict[str, str]:
        return {"source": _p.source, "identifier": _p.identifier}

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Any, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    if mock_api_key_service is None:
        mock_api_key_service = AsyncMock(spec=APIKeyAuthenticationService)
        mock_api_key_service.authenticate.return_value = _principal()

    if mock_jwt is None:
        mock_jwt = _mock_jwt_handler()

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_api_key_service(self) -> APIKeyAuthenticationService:
            return as_typed_mock(APIKeyAuthenticationService, mock_api_key_service)

        @provide(scope=Scope.APP)
        def get_jwt_handler(self) -> JWTHandler:
            return as_typed_mock(JWTHandler, mock_jwt)

    container = make_async_container(MockProvider())
    setup_dishka(container, app)
    return app


class TestGetCurrentPrincipalJWT:
    """JWT path in get_current_principal."""

    @patch("app.api.deps.get_settings")
    async def test_jwt_valid_user(self, mock_get_settings: Any) -> None:
        user_id = str(uuid4())
        mock_get_settings.return_value = _mock_settings("")
        mock_jwt = _mock_jwt_handler(user_id=user_id)

        app = _create_app_principal(mock_jwt=mock_jwt)
        resp = await _get(
            app, "/test-principal", {"Authorization": f"Bearer tok-{user_id}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "jwt"
        assert data["identifier"] == user_id

    @patch("app.api.deps.get_settings")
    async def test_jwt_master_key_claim(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("mk-123")
        mock_jwt = _mock_jwt_handler(
            claims={"sub": str(uuid4()), "x-api-key": "mk-123"}
        )

        app = _create_app_principal(mock_jwt=mock_jwt)
        resp = await _get(
            app, "/test-principal", {"Authorization": "Bearer tok-master"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["identifier"] == "master"

    @patch("app.api.deps.get_settings")
    async def test_invalid_jwt_fails_closed_when_api_key_is_also_present(
        self, mock_get_settings: Any
    ) -> None:
        mock_get_settings.return_value = _mock_settings("")
        mock_jwt = MagicMock(spec=JWTHandler)
        mock_jwt.decode_token.side_effect = Exception("bad token")

        mock_service = AsyncMock()
        mock_service.authenticate.return_value = _principal(scope="read-write")

        app = _create_app_principal(
            mock_api_key_service=mock_service, mock_jwt=mock_jwt
        )
        resp = await _get(
            app,
            "/test-principal",
            {
                "Authorization": "Bearer invalid-token",
                "X-API-Key": "nnk_validkey123",
            },
        )
        assert resp.status_code == 401
        mock_service.authenticate.assert_not_awaited()


class TestGetCurrentPrincipalAPIKey:
    """API key path in get_current_principal."""

    @patch("app.api.deps.get_settings")
    async def test_api_key_valid(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")

        app = _create_app_principal()
        resp = await _get(app, "/test-principal", {"X-API-Key": "nnk_validkey123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "api_key"
        assert data["identifier"] == "nnk_vali"

    @patch("app.api.deps.get_settings")
    async def test_api_key_master(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("test-master")

        app = _create_app_principal()
        resp = await _get(app, "/test-principal", {"X-API-Key": "test-master"})
        assert resp.status_code == 200
        assert resp.json()["identifier"] == "master"

    async def test_no_auth_returns_401(self) -> None:
        app = _create_app_principal()
        resp = await _get(app, "/test-principal")
        assert resp.status_code == 401
        assert "Not authenticated" in resp.json()["detail"]

    @patch("app.api.deps.get_settings")
    async def test_invalid_api_key_returns_401(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")
        mock_service = AsyncMock()
        mock_service.authenticate.side_effect = AuthenticationError("bad key")

        app = _create_app_principal(mock_api_key_service=mock_service)
        resp = await _get(app, "/test-principal", {"X-API-Key": "nnk_bad"})
        assert resp.status_code == 401


# --- require_write_or_jwt_scope tests ---


def _create_app_write_scope(
    mock_api_key_service: AsyncMock | None = None,
    mock_jwt: MagicMock | None = None,
) -> FastAPI:
    import fastapi
    from fastapi.responses import JSONResponse

    from app.api.deps import require_write_or_jwt_scope

    app = FastAPI()

    @app.get("/test-write")
    async def test_endpoint(
        _p: Principal = fastapi.Security(require_write_or_jwt_scope),
    ) -> dict[str, str]:
        return {"source": _p.source, "identifier": _p.identifier}

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Any, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    if mock_api_key_service is None:
        mock_api_key_service = AsyncMock(spec=APIKeyAuthenticationService)
        mock_api_key_service.authenticate.return_value = _principal()

    if mock_jwt is None:
        mock_jwt = _mock_jwt_handler()

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_api_key_service(self) -> APIKeyAuthenticationService:
            return as_typed_mock(APIKeyAuthenticationService, mock_api_key_service)

        @provide(scope=Scope.APP)
        def get_jwt_handler(self) -> JWTHandler:
            return as_typed_mock(JWTHandler, mock_jwt)

    container = make_async_container(MockProvider())
    setup_dishka(container, app)
    return app


class TestRequireWriteOrJwtScopeJWT:
    """JWT path in require_write_or_jwt_scope."""

    @patch("app.api.deps.get_settings")
    async def test_jwt_superuser_allowed(self, mock_get_settings: Any) -> None:
        user_id = str(uuid4())
        mock_get_settings.return_value = _mock_settings("")
        mock_jwt = _mock_jwt_handler(
            user_id=user_id,
            claims={"sub": user_id, "is_superuser": True, "type": "access"},
        )

        app = _create_app_write_scope(mock_jwt=mock_jwt)
        resp = await _get(
            app, "/test-write", {"Authorization": f"Bearer tok-{user_id}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "jwt"
        assert data["identifier"] == user_id

    @patch("app.api.deps.get_settings")
    async def test_jwt_non_superuser_denied(self, mock_get_settings: Any) -> None:
        user_id = str(uuid4())
        mock_get_settings.return_value = _mock_settings("")
        mock_jwt = _mock_jwt_handler(
            user_id=user_id,
            claims={"sub": user_id, "is_superuser": False, "type": "access"},
        )

        app = _create_app_write_scope(mock_jwt=mock_jwt)
        resp = await _get(
            app, "/test-write", {"Authorization": f"Bearer tok-{user_id}"}
        )
        assert resp.status_code == 403
        assert "Superuser" in resp.json()["detail"]

    @patch("app.api.deps.get_settings")
    async def test_invalid_jwt_fails_closed_when_write_key_is_also_present(
        self, mock_get_settings: Any
    ) -> None:
        mock_get_settings.return_value = _mock_settings("")
        mock_jwt = MagicMock(spec=JWTHandler)
        mock_jwt.decode_token.side_effect = Exception("bad")

        mock_service = AsyncMock()
        mock_service.authenticate.return_value = _principal(scope="read-write")

        app = _create_app_write_scope(
            mock_api_key_service=mock_service, mock_jwt=mock_jwt
        )
        resp = await _get(
            app,
            "/test-write",
            {
                "Authorization": "Bearer invalid-token",
                "X-API-Key": "nnk_validkey123",
            },
        )
        assert resp.status_code == 401
        mock_service.authenticate.assert_not_awaited()


class TestRequireWriteOrJwtScopeAPIKey:
    """API key path in require_write_or_jwt_scope."""

    @patch("app.api.deps.get_settings")
    async def test_write_key_allowed(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")
        app = _create_app_write_scope()
        resp = await _get(app, "/test-write", {"X-API-Key": "nnk_validkey123"})
        assert resp.status_code == 200

    @patch("app.api.deps.get_settings")
    async def test_read_only_key_denied(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("")
        mock_service = AsyncMock()
        mock_service.authenticate.return_value = _principal(scope="read-only")

        app = _create_app_write_scope(mock_api_key_service=mock_service)
        resp = await _get(app, "/test-write", {"X-API-Key": "nnk_readonly1"})
        assert resp.status_code == 403
        assert "read-only" in resp.json()["detail"].lower()

    @patch("app.api.deps.get_settings")
    async def test_master_key_allowed(self, mock_get_settings: Any) -> None:
        mock_get_settings.return_value = _mock_settings("test-master")
        app = _create_app_write_scope()
        resp = await _get(app, "/test-write", {"X-API-Key": "test-master"})
        assert resp.status_code == 200
        assert resp.json()["identifier"] == "master"


# --- _decode_access_token edge cases ---


class TestDecodeAccessToken:
    """Edge cases for _decode_access_token."""

    def test_non_string_sub_returns_401(self) -> None:
        from app.api.deps import _decode_access_token

        mock_jwt = MagicMock(spec=JWTHandler)
        mock_jwt.decode_token.return_value = {"sub": 12345}

        with pytest.raises(HTTPException) as exc_info:
            _decode_access_token(mock_jwt, "token")
        assert exc_info.value.status_code == 401

    def test_decode_exception_returns_401(self) -> None:
        from app.api.deps import _decode_access_token

        mock_jwt = MagicMock(spec=JWTHandler)
        mock_jwt.decode_token.side_effect = ValueError("expired")

        with pytest.raises(HTTPException) as exc_info:
            _decode_access_token(mock_jwt, "token")
        assert exc_info.value.status_code == 401


# --- password_hasher coverage ---


class TestPasswordHasher:
    def test_hash_and_verify(self) -> None:
        from app.adapters.security.password_hasher import PasswordHasherAdapter

        hasher = PasswordHasherAdapter()
        hashed = hasher.hash("mypassword")
        assert hasher.verify("mypassword", hashed)
        assert not hasher.verify("wrongpassword", hashed)


# --- health PackageNotFoundError ---


class TestHealthVersion:
    @patch("app.api.v2.health.pkg_version", side_effect=PackageNotFoundError)
    def test_version_unknown_on_exception(self, mock_pkg_version: Any) -> None:
        from app.api.v2.health import _get_app_version

        result = _get_app_version()
        assert result == "unknown"
