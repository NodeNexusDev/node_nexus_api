"""Unit tests for timeout middleware."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.middleware import TimeoutMiddleware
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.application.services.node_management_service import NodeManagementService
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_test_app(node_service: NodeManagementService | AsyncMock) -> FastAPI:
    """Create a test app with mocked NodeManagementService and TimeoutMiddleware."""
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    app.add_middleware(TimeoutMiddleware, timeout=1)

    class MockNodeManagementServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> NodeManagementService:
            return as_typed_mock(NodeManagementService, node_service)

    container = make_async_container(
        MockNodeManagementServiceProvider(), MockAuthServiceProvider()
    )
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create a mock NodeManagementService."""
    return AsyncMock(spec=NodeManagementService)


@pytest.fixture
async def client(mock_service: AsyncMock) -> AsyncGenerator[AsyncClient]:
    """Create a client with mocked node management and a short timeout."""
    app = _create_test_app(mock_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


async def test_health_endpoint_no_timeout(client: AsyncClient) -> None:
    """GET /health should not be affected by timeout middleware."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


async def test_ready_endpoint_no_timeout(client: AsyncClient) -> None:
    """GET /ready should not be affected by timeout middleware."""
    from app.application.services.health_service import HealthService

    mock_health = AsyncMock(spec=HealthService)
    mock_health.check_db.return_value = ("ok", "database reachable")
    mock_health.check_scheduler = MagicMock(return_value=("ok", "scheduler disabled"))

    app = FastAPI()
    app.include_router(health_router)
    app.add_middleware(TimeoutMiddleware, timeout=1)

    class MockHealthServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> HealthService:
            return as_typed_mock(HealthService, mock_health)

    container = make_async_container(MockHealthServiceProvider())
    setup_dishka(container, app)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/ready")
    assert resp.status_code == 200


async def test_timeout_middleware_excludes_health(
    client: AsyncClient, mock_service: AsyncMock
) -> None:
    """Timeout middleware should exclude /health path."""
    mock_service.get_node.return_value = AsyncMock()
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_timeout_middleware_excludes_ready(
    client: AsyncClient, mock_service: AsyncMock
) -> None:
    """Timeout middleware should exclude /ready path."""
    from app.application.services.health_service import HealthService

    mock_health = AsyncMock(spec=HealthService)
    mock_health.check_db.return_value = ("ok", "database reachable")
    mock_health.check_scheduler = MagicMock(return_value=("ok", "scheduler disabled"))

    app = FastAPI()
    app.include_router(health_router)
    app.add_middleware(TimeoutMiddleware, timeout=1)

    class MockHealthServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> HealthService:
            return as_typed_mock(HealthService, mock_health)

    container = make_async_container(MockHealthServiceProvider())
    setup_dishka(container, app)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/ready")
    assert resp.status_code == 200


async def test_timeout_middleware_init() -> None:
    """TimeoutMiddleware can be initialized with custom timeout."""
    from starlette.applications import Starlette

    app = Starlette()
    middleware = TimeoutMiddleware(app, timeout=60)
    assert middleware._timeout == 60


async def test_timeout_middleware_default_timeout() -> None:
    """TimeoutMiddleware has a default timeout of 300 seconds."""
    from starlette.applications import Starlette

    app = Starlette()
    middleware = TimeoutMiddleware(app)
    assert middleware._timeout == 300
