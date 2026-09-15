"""Unit tests for tag-vocabulary endpoints with mocked services via dishka."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v2.commands_handlers.listing import router as commands_listing_router
from app.api.v2.nodes_handlers.listing import router as nodes_listing_router
from app.api.v2.scripts_handlers.listing import router as scripts_listing_router
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.command_management_service import (
    CommandManagementService,
)
from app.application.services.node_management_service import NodeManagementService
from app.application.services.script_management_service import ScriptManagementService
from app.core.config import Settings, get_settings
from tests.typing import as_typed_mock


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


def _create_test_app(
    node_service: Any,
    command_service: Any,
    script_service: Any,
) -> FastAPI:
    app = FastAPI()
    app.include_router(nodes_listing_router, prefix="/nodes")
    app.include_router(commands_listing_router, prefix="/commands")
    app.include_router(scripts_listing_router, prefix="/scripts")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_node_service(self) -> NodeManagementService:
            return as_typed_mock(NodeManagementService, node_service)

        @provide(scope=Scope.REQUEST)
        def get_command_service(self) -> CommandManagementService:
            return as_typed_mock(CommandManagementService, command_service)

        @provide(scope=Scope.REQUEST)
        def get_script_service(self) -> ScriptManagementService:
            return as_typed_mock(ScriptManagementService, script_service)

        @provide(scope=Scope.REQUEST)
        def get_auth_service(self) -> APIKeyAuthenticationService:
            return as_typed_mock(
                APIKeyAuthenticationService,
                AsyncMock(spec=APIKeyAuthenticationService),
            )

        @provide(scope=Scope.APP)
        def get_jwt_handler(self) -> JWTHandler:
            return as_typed_mock(JWTHandler, MagicMock(spec=JWTHandler))

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:
            return get_settings()

    container = make_async_container(MockServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_services() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    return (
        AsyncMock(spec=NodeManagementService),
        AsyncMock(spec=CommandManagementService),
        AsyncMock(spec=ScriptManagementService),
    )


@patch("app.core.config.get_settings")
async def test_node_tags(
    mock_get_settings: Any, mock_services: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    mock_get_settings.return_value = _mock_settings("test-master-key")
    node_service, command_service, script_service = mock_services
    node_service.get_all_tags.return_value = ["alpha", "beta"]
    app = _create_test_app(node_service, command_service, script_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        response = await ac.get("/nodes/tags", headers={"X-API-Key": "test-master-key"})
    assert response.status_code == 200
    assert response.json() == ["alpha", "beta"]
    node_service.get_all_tags.assert_awaited_once_with()


@patch("app.core.config.get_settings")
async def test_command_tags(
    mock_get_settings: Any, mock_services: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    mock_get_settings.return_value = _mock_settings("test-master-key")
    node_service, command_service, script_service = mock_services
    command_service.get_all_tags.return_value = ["ops"]
    app = _create_test_app(node_service, command_service, script_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        response = await ac.get(
            "/commands/tags", headers={"X-API-Key": "test-master-key"}
        )
    assert response.status_code == 200
    assert response.json() == ["ops"]
    command_service.get_all_tags.assert_awaited_once_with()


@patch("app.core.config.get_settings")
async def test_script_tags(
    mock_get_settings: Any, mock_services: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    mock_get_settings.return_value = _mock_settings("test-master-key")
    node_service, command_service, script_service = mock_services
    script_service.get_all_tags.return_value = []
    app = _create_test_app(node_service, command_service, script_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        response = await ac.get(
            "/scripts/tags", headers={"X-API-Key": "test-master-key"}
        )
    assert response.status_code == 200
    assert response.json() == []
    script_service.get_all_tags.assert_awaited_once_with()


@patch("app.core.config.get_settings")
async def test_tags_require_auth(
    mock_get_settings: Any, mock_services: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    mock_get_settings.return_value = _mock_settings("test-master-key")
    app = _create_test_app(*mock_services)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        for path in ("/nodes/tags", "/commands/tags", "/scripts/tags"):
            response = await ac.get(path)
            assert response.status_code == 401
