"""Tests for script schedule API endpoints via test client."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.scripts import router as scripts_router
from app.core.exceptions import ScriptNotFoundError
from app.core.scheduler import ScriptScheduler
from app.services.script_service import ScriptService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_test_app(
    service: ScriptService, scheduler: ScriptScheduler | None = None
) -> FastAPI:
    app = FastAPI()
    app.include_router(scripts_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> ScriptService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_scheduler(self) -> ScriptScheduler:
            return scheduler if scheduler is not None else ScriptScheduler()

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=ScriptService)


@pytest.fixture
def mock_scheduler() -> MagicMock:
    scheduler = MagicMock(spec=ScriptScheduler)
    scheduler.schedule_script.return_value = "job-123"
    scheduler.unschedule_script.return_value = True
    scheduler.get_schedule.return_value = {
        "script_id": "00000000-0000-0000-0000-000000000001",
        "cron": "0 9 * * *",
        "node_ids": ["00000000-0000-0000-0000-000000000002"],
    }
    return scheduler


@pytest.fixture
async def client(
    mock_service: AsyncMock, mock_scheduler: MagicMock
) -> AsyncGenerator[AsyncClient]:
    app = _create_test_app(mock_service, mock_scheduler)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


@pytest.mark.asyncio
class TestScheduleScriptAPI:
    async def test_schedule_script(self, client: AsyncClient, mock_service: AsyncMock):
        """POST /api/v1/scripts/{id}/schedule schedules a script."""
        mock_service.get_script.return_value = MagicMock()

        node_id = "00000000-0000-0000-0000-000000000002"
        schedule_json = {"cron": "0 9 * * *", "node_ids": [node_id]}

        resp = await client.post(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule",
            json=schedule_json,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cron"] == "0 9 * * *"

    async def test_schedule_script_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """POST /api/v1/scripts/{id}/schedule returns 404."""
        mock_service.get_script.side_effect = ScriptNotFoundError("not found")

        node_id = "00000000-0000-0000-0000-000000000002"
        schedule_json = {"cron": "0 9 * * *", "node_ids": [node_id]}

        resp = await client.post(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule",
            json=schedule_json,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestUnscheduleScriptAPI:
    async def test_unschedule_script(
        self, client: AsyncClient, mock_scheduler: MagicMock
    ):
        """DELETE /api/v1/scripts/{id}/schedule removes schedule."""
        mock_scheduler.unschedule_script.return_value = True

        resp = await client.delete(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 200
        assert "unscheduled" in resp.json()["message"]

    async def test_unschedule_not_found(
        self, client: AsyncClient, mock_scheduler: MagicMock
    ):
        """DELETE /api/v1/scripts/{id}/schedule returns 404."""
        mock_scheduler.unschedule_script.return_value = False

        resp = await client.delete(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestGetScheduleAPI:
    async def test_get_schedule(self, client: AsyncClient, mock_scheduler: MagicMock):
        """GET /api/v1/scripts/{id}/schedule returns schedule info."""
        mock_scheduler.get_schedule.return_value = {
            "script_id": "abc",
            "cron": "0 9 * * *",
        }

        resp = await client.get(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 200
        assert resp.json()["cron"] == "0 9 * * *"

    async def test_get_schedule_not_found(
        self, client: AsyncClient, mock_scheduler: MagicMock
    ):
        """GET /api/v1/scripts/{id}/schedule returns 404."""
        mock_scheduler.get_schedule.return_value = None

        resp = await client.get(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 404
