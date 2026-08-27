"""Unit tests for users API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest  # noqa: F401
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx2 import ASGITransport, AsyncClient

from app.application.dto.user import UserPageDTO, UserViewDTO
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.user_service import UserService
from app.core.exceptions import (
    DomainError,
    InsufficientPermissionsError,
    UserAlreadyExistsError,
    UserNotFoundError,
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


def _mock_jwt_handler(is_superuser: bool = True) -> MagicMock:
    handler = MagicMock(spec=JWTHandler)
    handler.decode_token.return_value = {
        "sub": str(uuid4()),
        "email": "admin@example.com",
        "is_superuser": is_superuser,
        "type": "access",
    }
    handler.hash_token.return_value = "hashed"
    return handler


def _create_app(
    mock_service: UserService | AsyncMock | None = None,
    mock_jwt: MagicMock | None = None,
    is_superuser: bool = True,
) -> FastAPI:
    from app.api.v1.users import router

    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request, exc: DomainError):
        status_map = {
            InsufficientPermissionsError: 403,
            UserAlreadyExistsError: 409,
            UserNotFoundError: 404,
        }
        return JSONResponse(
            status_code=status_map.get(type(exc), 422),
            content={"detail": str(exc)},
        )

    if mock_service is None:
        mock_service = AsyncMock(spec=UserService)
        mock_service.list_users.return_value = UserPageDTO(
            items=(_user_view(),), total=1
        )
        mock_service.create_user.return_value = _user_view()
        mock_service.delete_user.return_value = True

    if mock_jwt is None:
        mock_jwt = _mock_jwt_handler(is_superuser=is_superuser)

    from app.application.services.api_key_authentication import (
        APIKeyAuthenticationService,
    )

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_user_service(self) -> UserService:
            return mock_service

        @provide(scope=Scope.APP)
        def get_jwt_handler(self) -> JWTHandler:
            return mock_jwt

        @provide(scope=Scope.APP)
        def get_api_key_service(self) -> APIKeyAuthenticationService:
            mock = AsyncMock(spec=APIKeyAuthenticationService)
            return mock

    container = make_async_container(MockProvider())
    setup_dishka(container, app)
    return app


async def _get(app: FastAPI, path: str, **kwargs) -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.get(path, **kwargs)
        body = {}
        if resp.content:
            try:
                body = resp.json()
            except Exception:
                pass
        return {"status": resp.status_code, "json": body}


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
        return {"status": resp.status_code, "json": body}


async def _delete(app: FastAPI, path: str, **kwargs) -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.delete(path, **kwargs)
        return {"status": resp.status_code}


class TestListUsers:
    async def test_no_auth(self) -> None:
        app = _create_app()
        result = await _get(app, "/users/")
        assert result["status"] == 401

    async def test_not_superuser(self) -> None:
        app = _create_app(is_superuser=False)
        result = await _get(app, "/users/", headers={"Authorization": "Bearer token"})
        assert result["status"] == 403

    async def test_success(self) -> None:
        app = _create_app()
        result = await _get(app, "/users/", headers={"Authorization": "Bearer token"})
        assert result["status"] == 200
        assert result["json"]["total"] == 1

    async def test_pagination_is_forwarded(self) -> None:
        mock_service = AsyncMock(spec=UserService)
        mock_service.list_users.return_value = UserPageDTO(items=(), total=25)
        app = _create_app(mock_service=mock_service)

        result = await _get(
            app,
            "/users/?page=2&size=10",
            headers={"Authorization": "Bearer token"},
        )

        assert result["status"] == 200
        mock_service.list_users.assert_awaited_once_with(
            offset=10,
            limit=10,
            caller_is_superuser=True,
        )


class TestCreateUser:
    async def test_no_auth(self) -> None:
        app = _create_app()
        result = await _post(
            app,
            "/users/",
            json={"email": "new@x.com", "password": "strong-password"},
        )
        assert result["status"] == 401

    async def test_not_superuser(self) -> None:
        app = _create_app(is_superuser=False)
        result = await _post(
            app,
            "/users/",
            json={"email": "new@x.com", "password": "strong-password"},
            headers={"Authorization": "Bearer token"},
        )
        assert result["status"] == 403

    async def test_duplicate_email(self) -> None:
        mock_service = AsyncMock(spec=UserService)
        mock_service.create_user.side_effect = UserAlreadyExistsError("already exists")
        app = _create_app(mock_service=mock_service)
        result = await _post(
            app,
            "/users/",
            json={"email": "dup@x.com", "password": "strong-password"},
            headers={"Authorization": "Bearer token"},
        )
        assert result["status"] == 409

    async def test_success(self) -> None:
        app = _create_app()
        result = await _post(
            app,
            "/users/",
            json={"email": "new@x.com", "password": "strong-password"},
            headers={"Authorization": "Bearer token"},
        )
        assert result["status"] == 201
        assert result["json"]["email"] == "test@example.com"


class TestDeleteUser:
    async def test_no_auth(self) -> None:
        app = _create_app()
        user_id = uuid4()
        result = await _delete(app, f"/users/{user_id}")
        assert result["status"] == 401

    async def test_not_superuser(self) -> None:
        app = _create_app(is_superuser=False)
        user_id = uuid4()
        result = await _delete(
            app, f"/users/{user_id}", headers={"Authorization": "Bearer token"}
        )
        assert result["status"] == 403

    async def test_user_not_found(self) -> None:
        mock_service = AsyncMock(spec=UserService)
        mock_service.delete_user.side_effect = UserNotFoundError("not found")
        app = _create_app(mock_service=mock_service)
        user_id = uuid4()
        result = await _delete(
            app, f"/users/{user_id}", headers={"Authorization": "Bearer token"}
        )
        assert result["status"] == 404

    async def test_success(self) -> None:
        app = _create_app()
        user_id = uuid4()
        result = await _delete(
            app, f"/users/{user_id}", headers={"Authorization": "Bearer token"}
        )
        assert result["status"] == 204
