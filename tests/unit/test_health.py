"""Unit tests for health check endpoints."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.health import router as health_router
from app.application.services.health_service import HealthService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_test_app(health_service: HealthService | AsyncMock) -> FastAPI:
    """Create a test app with mocked HealthService."""
    app = FastAPI()
    app.include_router(health_router)

    class MockHealthServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> HealthService:
            return health_service

    container = make_async_container(
        MockHealthServiceProvider(), MockAuthServiceProvider()
    )
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create a mock HealthService."""
    return AsyncMock(spec=HealthService)


@pytest.fixture
async def client(mock_service: AsyncMock) -> AsyncGenerator[AsyncClient]:
    """Create an async test client with mocked HealthService."""
    app = _create_test_app(mock_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


@pytest.fixture
async def client_no_auth(mock_service: AsyncMock) -> AsyncGenerator[AsyncClient]:
    """Create an async test client without authentication."""
    app = _create_test_app(mock_service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac


# --- GET /health ---


async def test_health_check_returns_healthy(client: AsyncClient) -> None:
    """GET /health returns 200 with healthy status."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


async def test_health_check_no_auth_required(client_no_auth: AsyncClient) -> None:
    """GET /health works without API key."""
    resp = await client_no_auth.get("/health")
    assert resp.status_code == 200


async def test_health_check_has_version(client: AsyncClient) -> None:
    """GET /health includes version in response."""
    resp = await client.get("/health")
    data = resp.json()
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


# --- GET /ready ---


async def test_readiness_check_db_ok(
    client: AsyncClient, mock_service: AsyncMock
) -> None:
    """GET /ready returns 200 when database is reachable."""
    mock_service.check_db.return_value = ("ok", "database reachable")
    mock_service.check_scheduler = MagicMock(return_value=("ok", "scheduler disabled"))
    resp = await client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["status"] == "ok"
    assert data["checks"]["database"]["detail"] == "database reachable"


async def test_readiness_check_db_down(
    client: AsyncClient, mock_service: AsyncMock
) -> None:
    """GET /ready returns 503 when database is unreachable."""
    mock_service.check_db.return_value = ("error", "OperationalError")
    mock_service.check_scheduler = MagicMock(return_value=("ok", "scheduler disabled"))
    resp = await client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["status"] == "error"


async def test_readiness_check_no_auth_required(
    client_no_auth: AsyncClient, mock_service: AsyncMock
) -> None:
    """GET /ready works without API key."""
    mock_service.check_db.return_value = ("ok", "database reachable")
    mock_service.check_scheduler = MagicMock(return_value=("ok", "scheduler disabled"))
    resp = await client_no_auth.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
