"""Unit tests for API key management endpoints with mocked services via dishka."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.api_keys import router as api_keys_router
from app.core.exceptions import APIKeyNotFoundError
from app.schemas.api_key import APIKeyCreated, APIKeyList, APIKeyResponse
from app.services.api_key_service import APIKeyService


def _make_api_key_response(**overrides: Any) -> APIKeyResponse:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "test-key",
        "key_prefix": "nnk_abcd",
        "is_active": True,
        "created_at": datetime.now(UTC),
        "last_used_at": None,
    }
    defaults.update(overrides)
    return APIKeyResponse(**defaults)


def _make_api_key_created(**overrides: Any) -> APIKeyCreated:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "test-key",
        "key": "nnk_abc123def456",
        "key_prefix": "nnk_abcd",
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return APIKeyCreated(**defaults)


def _create_test_app(service: APIKeyService | AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(api_keys_router)

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> APIKeyService:
            return service

    container = make_async_container(MockServiceProvider())
    setup_dishka(container, app)
    return app


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


class MockSessionContext:
    def __init__(self, return_value: Any) -> None:
        self._return_value = return_value

    async def __aenter__(self) -> Any:
        return self._return_value

    async def __aexit__(self, *args: Any) -> None:
        pass


class MockSession:
    def __init__(self, execute_result: Any = None) -> None:
        self._execute_result = execute_result

    async def execute(self, *args: Any) -> MagicMock:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self._execute_result
        return mock_result

    async def flush(self) -> None:
        pass

    def begin(self) -> MockSessionContext:
        return MockSessionContext(self)


class MockSessionmaker:
    def __init__(self, execute_result: Any = None) -> None:
        self._execute_result = execute_result

    def __call__(self) -> MockSessionContext:
        return MockSessionContext(MockSession(self._execute_result))


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=APIKeyService)


# --- POST /api-keys/ ---


class TestCreateApiKey:
    @patch("app.api.deps.get_settings")
    async def test_success(
        self, mock_get_settings: Any, mock_service: AsyncMock
    ) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-key")
        app = _create_test_app(mock_service)
        app.state.sessionmaker = MockSessionmaker()

        mock_service.create_api_key.side_effect = (
            lambda name: _make_api_key_created(name=name)
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            response = await ac.post(
                "/api-keys/",
                json={"name": "my-key"},
                headers={"X-API-Key": "test-master-key"},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "my-key"
        assert data["key"] == "nnk_abc123def456"
        mock_service.create_api_key.assert_called_once_with("my-key")

    @patch("app.api.deps.get_settings")
    async def test_validation_error(
        self, mock_get_settings: Any, mock_service: AsyncMock
    ) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-key")
        app = _create_test_app(mock_service)
        app.state.sessionmaker = MockSessionmaker()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            response = await ac.post(
                "/api-keys/",
                json={"name": ""},
                headers={"X-API-Key": "test-master-key"},
            )
        assert response.status_code == 422


# --- GET /api-keys/ ---


class TestListApiKeys:
    @patch("app.api.deps.get_settings")
    async def test_empty(
        self, mock_get_settings: Any, mock_service: AsyncMock
    ) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-key")
        app = _create_test_app(mock_service)
        app.state.sessionmaker = MockSessionmaker()
        mock_service.list_api_keys.return_value = APIKeyList(items=[], total=0)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            response = await ac.get(
                "/api-keys/",
                headers={"X-API-Key": "test-master-key"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @patch("app.api.deps.get_settings")
    async def test_with_data(
        self, mock_get_settings: Any, mock_service: AsyncMock
    ) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-key")
        app = _create_test_app(mock_service)
        app.state.sessionmaker = MockSessionmaker()
        keys = [_make_api_key_response(name="k1"), _make_api_key_response(name="k2")]
        mock_service.list_api_keys.return_value = APIKeyList(items=keys, total=2)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            response = await ac.get(
                "/api-keys/",
                headers={"X-API-Key": "test-master-key"},
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    @patch("app.api.deps.get_settings")
    async def test_pagination(
        self, mock_get_settings: Any, mock_service: AsyncMock
    ) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-key")
        app = _create_test_app(mock_service)
        app.state.sessionmaker = MockSessionmaker()
        mock_service.list_api_keys.return_value = APIKeyList(items=[], total=0)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            await ac.get(
                "/api-keys/?page=2&size=10",
                headers={"X-API-Key": "test-master-key"},
            )
        mock_service.list_api_keys.assert_called_once_with(page=2, size=10)


# --- DELETE /api-keys/{id} ---


class TestRevokeApiKey:
    @patch("app.api.deps.get_settings")
    async def test_success(
        self, mock_get_settings: Any, mock_service: AsyncMock
    ) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-key")
        app = _create_test_app(mock_service)
        app.state.sessionmaker = MockSessionmaker()
        mock_service.revoke_api_key.return_value = None
        key_id = uuid.uuid4()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            response = await ac.delete(
                f"/api-keys/{key_id}",
                headers={"X-API-Key": "test-master-key"},
            )
        assert response.status_code == 204
        mock_service.revoke_api_key.assert_called_once_with(key_id)

    @patch("app.api.deps.get_settings")
    async def test_not_found(
        self, mock_get_settings: Any, mock_service: AsyncMock
    ) -> None:
        mock_get_settings.return_value = _mock_settings("test-master-key")
        app = _create_test_app(mock_service)
        app.state.sessionmaker = MockSessionmaker()
        mock_service.revoke_api_key.side_effect = APIKeyNotFoundError("not found")

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            response = await ac.delete(
                f"/api-keys/{uuid.uuid4()}",
                headers={"X-API-Key": "test-master-key"},
            )
        assert response.status_code == 404
