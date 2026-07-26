"""Tests for config export/import API endpoints via test client."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.config import router as config_router
from app.schemas.config import ConfigExport, ImportResult
from app.services.config_service import ConfigService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_test_app(service: ConfigService) -> FastAPI:
    app = FastAPI()
    app.include_router(config_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> ConfigService:
            return service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=ConfigService)


@pytest.fixture
async def client(mock_service: AsyncMock) -> AsyncGenerator[AsyncClient]:
    app = _create_test_app(mock_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


@pytest.mark.asyncio
class TestConfigExportAPI:
    async def test_export_config(self, client: AsyncClient, mock_service: AsyncMock):
        """GET /api/v1/config/export returns export data."""
        mock_service.export_all.return_value = ConfigExport(
            exported_at="2026-01-01T00:00:00Z"
        )
        resp = await client.get("/api/v1/config/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "0.5.0"
        assert "exported_at" in data


@pytest.mark.asyncio
class TestConfigImportAPI:
    async def test_import_config(self, client: AsyncClient, mock_service: AsyncMock):
        """POST /api/v1/config/import imports data."""
        mock_service.import_config.return_value = ImportResult(nodes_created=2)
        resp = await client.post(
            "/api/v1/config/import",
            json={"nodes": [], "commands": [], "scripts": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes_created"] == 2

    async def test_import_empty_payload(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """POST /api/v1/config/import with empty payload."""
        mock_service.import_config.return_value = ImportResult()
        resp = await client.post(
            "/api/v1/config/import",
            json={},
        )
        assert resp.status_code == 200
