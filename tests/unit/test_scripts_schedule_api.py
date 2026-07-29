"""Tests for script schedule API endpoints via test client."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.api.v1.scripts import router as scripts_router
from app.core.exceptions import DomainError, ScheduleNotFoundError, ScriptNotFoundError
from app.schemas.scheduler import ScheduledJob
from app.services.schedule_service import ScheduleService
from app.services.script_execution_service import ScriptExecutionService
from app.services.script_history_service import ScriptHistoryService
from app.services.script_management_service import ScriptManagementService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_test_app(service: AsyncMock, schedule_service: ScheduleService) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(scripts_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_management_service(self) -> ScriptManagementService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_history_service(self) -> ScriptHistoryService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_execution_service(self) -> ScriptExecutionService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_schedule_service(self) -> ScheduleService:
            return schedule_service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_schedule_service() -> AsyncMock:
    service = AsyncMock(spec=ScheduleService)
    service.create_or_update.return_value = ScheduledJob(
        id="00000000-0000-0000-0000-000000000003",
        script_id="00000000-0000-0000-0000-000000000001",
        cron="0 9 * * *",
        timezone="UTC",
        node_ids=["00000000-0000-0000-0000-000000000002"],
        params={},
        enabled=True,
        misfire_grace_seconds=60,
        operational_state="registered",
    )
    service.get.return_value = service.create_or_update.return_value
    return service


@pytest.fixture
async def client(
    mock_service: AsyncMock, mock_schedule_service: AsyncMock
) -> AsyncGenerator[AsyncClient]:
    app = _create_test_app(mock_service, mock_schedule_service)
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
        self, client: AsyncClient, mock_schedule_service: AsyncMock
    ):
        """POST /api/v1/scripts/{id}/schedule returns 404."""
        mock_schedule_service.create_or_update.side_effect = ScriptNotFoundError(
            "not found"
        )

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
        self, client: AsyncClient, mock_schedule_service: AsyncMock
    ):
        """DELETE /api/v1/scripts/{id}/schedule removes schedule."""
        resp = await client.delete(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 200
        assert "unscheduled" in resp.json()["message"]

    async def test_unschedule_not_found(
        self, client: AsyncClient, mock_schedule_service: AsyncMock
    ):
        """DELETE /api/v1/scripts/{id}/schedule returns 404."""
        mock_schedule_service.delete.side_effect = ScheduleNotFoundError("missing")

        resp = await client.delete(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestGetScheduleAPI:
    async def test_get_schedule(
        self, client: AsyncClient, mock_schedule_service: AsyncMock
    ):
        """GET /api/v1/scripts/{id}/schedule returns schedule info."""
        resp = await client.get(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 200
        assert resp.json()["cron"] == "0 9 * * *"

    async def test_get_schedule_not_found(
        self, client: AsyncClient, mock_schedule_service: AsyncMock
    ):
        """GET /api/v1/scripts/{id}/schedule returns 404."""
        mock_schedule_service.get.side_effect = ScheduleNotFoundError("missing")

        resp = await client.get(
            "/api/v1/scripts/00000000-0000-0000-0000-000000000001/schedule"
        )
        assert resp.status_code == 404
