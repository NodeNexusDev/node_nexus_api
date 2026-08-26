"""Unit tests for auth API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest  # noqa: F401
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx2 import ASGITransport, AsyncClient

from app.application.dto.user import UserViewDTO
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.auth_service import AuthService
from app.core.exceptions import (
    DomainError,
    InvalidCredentialsError,
    TokenExpiredError,
)


def _user_view(**overrides) -> UserViewDTO:
    defaults = {
        "id": uuid4(),
        "email": "test@example.com",
        "is_active": True,
        "is_superuser": False,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return UserViewDTO(**defaults)


def _mock_jwt_handler() -> MagicMock:
    handler = MagicMock(spec=JWTHandler)
    handler.encode_access_token.return_value = "access-token"
    handler.encode_refresh_token.return_value = "refresh-token"
    handler.hash_token.return_value = "hashed-refresh"
    handler.decode_token.return_value = {
        "sub": str(uuid4()),
        "email": "test@example.com",
        "is_superuser": False,
        "type": "access",
    }
    return handler


def _create_app(
    mock_service: AuthService | AsyncMock | None = None,
    mock_jwt: MagicMock | None = None,
) -> FastAPI:
    from app.api.v1.auth import router

    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request, exc: DomainError):
        status_map = {
            InvalidCredentialsError: 401,
            TokenExpiredError: 401,
        }
        return JSONResponse(
            status_code=status_map.get(type(exc), 422),
            content={"detail": str(exc)},
        )

    if mock_service is None:
        mock_service = AsyncMock(spec=AuthService)
        mock_service.login.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "bearer",
        }
        mock_service.refresh_access_token.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "token_type": "bearer",
        }
        mock_service.get_current_user.return_value = _user_view()

    if mock_jwt is None:
        mock_jwt = _mock_jwt_handler()

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_auth_service(self) -> AuthService:
            return mock_service

        @provide(scope=Scope.APP)
        def get_jwt_handler(self) -> JWTHandler:
            return mock_jwt

        @provide(scope=Scope.REQUEST)
        def get_api_key_service(self) -> APIKeyAuthenticationService:
            return AsyncMock(spec=APIKeyAuthenticationService)

    container = make_async_container(MockProvider())
    setup_dishka(container, app)
    return app


async def _post(app: FastAPI, path: str, **kwargs) -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.post(path, **kwargs)
        body = {}
        if resp.content:
            try:
                body = resp.json()
            except Exception:
                pass
        return {"status": resp.status_code, "json": body, "cookies": dict(resp.cookies)}


async def _get(app: FastAPI, path: str, **kwargs) -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.get(path, **kwargs)
        return {"status": resp.status_code, "json": resp.json()}


class TestLoginEndpoint:
    async def test_invalid_credentials(self) -> None:
        mock_service = AsyncMock(spec=AuthService)
        mock_service.login.side_effect = InvalidCredentialsError("Invalid")
        app = _create_app(mock_service=mock_service)

        result = await _post(
            app, "/auth/login", json={"email": "x@x.com", "password": "wrong"}
        )
        assert result["status"] == 401
        assert "Invalid" in result["json"]["detail"]

    async def test_success_sets_cookie(self) -> None:
        app = _create_app()
        result = await _post(
            app, "/auth/login", json={"email": "test@example.com", "password": "pass"}
        )
        assert result["status"] == 200
        assert result["json"]["access_token"] == "access-token"
        assert result["json"]["token_type"] == "bearer"
        assert "refresh_token" in result["cookies"]


class TestLogoutEndpoint:
    async def test_clears_cookie(self) -> None:
        app = _create_app()
        result = await _post(app, "/auth/logout")
        assert result["status"] == 204


class TestRefreshEndpoint:
    async def test_missing_cookie(self) -> None:
        app = _create_app()
        result = await _post(app, "/auth/refresh")
        assert result["status"] == 401

    async def test_invalid_token(self) -> None:
        mock_service = AsyncMock(spec=AuthService)
        mock_service.refresh_access_token.side_effect = TokenExpiredError("Invalid")
        app = _create_app(mock_service=mock_service)

        result = await _post(app, "/auth/refresh", cookies={"refresh_token": "invalid"})
        assert result["status"] == 401

    async def test_success(self) -> None:
        app = _create_app()
        result = await _post(
            app, "/auth/refresh", cookies={"refresh_token": "valid-token"}
        )
        assert result["status"] == 200
        assert result["json"]["access_token"] == "new-access-token"
        assert "refresh_token" in result["cookies"]


class TestMeEndpoint:
    async def test_no_token(self) -> None:
        app = _create_app()
        result = await _get(app, "/auth/me")
        assert result["status"] == 401

    async def test_success(self) -> None:
        app = _create_app()
        result = await _get(
            app, "/auth/me", headers={"Authorization": "Bearer valid-token"}
        )
        assert result["status"] == 200
        assert result["json"]["email"] == "test@example.com"
