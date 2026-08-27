"""Unit tests for internal API endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.internal import router as internal_router
from app.application.ports.audit_outbox_controller import AuditOutboxController
from app.application.ports.schedule import JobSchedulerPort, ScheduleReader
from app.application.services.scheduled_script_executor import ScheduledScriptExecutor
from app.core.config import Settings
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_internal_app(**services: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(internal_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_audit_controller(self) -> AuditOutboxController:
            return services.get("audit_controller", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_job_scheduler(self) -> JobSchedulerPort:
            return services.get("job_scheduler", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_schedule_reader(self) -> ScheduleReader:
            return services.get("schedule_reader", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_executor(self) -> ScheduledScriptExecutor:
            return services.get("executor", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_settings(self) -> Settings:
            return services.get("settings", _mock_settings("test-master"))

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


SCRIPT_ID = "00000000-0000-0000-0000-000000000001"

_settings_patcher = patch(
    "app.api.deps.get_settings",
    return_value=_mock_settings("test-master"),
)


class TestPauseBackground:
    @pytest.mark.asyncio
    async def test_pause_background_tasks(self) -> None:
        svc = AsyncMock()
        svc.pause.return_value = None
        app = _create_internal_app(audit_controller=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v1/internal/e2e/pause-background")
        assert resp.status_code == 200


class TestResumeBackground:
    @pytest.mark.asyncio
    async def test_resume_background_tasks(self) -> None:
        svc = AsyncMock()
        svc.start = MagicMock()
        svc.resume.return_value = None
        app = _create_internal_app(audit_controller=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v1/internal/e2e/resume-background")
        assert resp.status_code == 200


class TestTriggerScheduledScript:
    @pytest.mark.asyncio
    async def test_trigger_scheduled_script_now(self) -> None:
        scheduler = AsyncMock()
        scheduler.owns_execution = True
        schedule_reader = AsyncMock()
        schedule_reader.get_schedule = AsyncMock(
            return_value=MagicMock(
                id=uuid.UUID(SCRIPT_ID),
                params={"key": "value"},
                node_ids=[uuid.UUID(SCRIPT_ID)],
            )
        )
        executor = AsyncMock()
        executor.execute = AsyncMock(return_value=None)
        settings = MagicMock()
        settings.E2E_ENABLED = True
        app = _create_internal_app(
            job_scheduler=scheduler,
            schedule_reader=schedule_reader,
            executor=executor,
            settings=settings,
        )
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v1/internal/e2e/scheduler/{SCRIPT_ID}/trigger-now",
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"


class TestTriggerNotFound:
    @pytest.mark.asyncio
    async def test_trigger_scheduled_script_not_found(self) -> None:
        scheduler = AsyncMock()
        scheduler.owns_execution = True
        schedule_reader = AsyncMock()
        schedule_reader.get_schedule = AsyncMock(return_value=None)
        executor = AsyncMock()
        settings = MagicMock()
        settings.E2E_ENABLED = True
        app = _create_internal_app(
            job_scheduler=scheduler,
            schedule_reader=schedule_reader,
            executor=executor,
            settings=settings,
        )
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v1/internal/e2e/scheduler/{SCRIPT_ID}/trigger-now",
                )
        assert resp.status_code == 404


class TestTriggerDisabled:
    @pytest.mark.asyncio
    async def test_trigger_scheduled_script_disabled(self) -> None:
        scheduler = AsyncMock()
        scheduler.owns_execution = True
        schedule_reader = AsyncMock()
        executor = AsyncMock()
        settings = MagicMock()
        settings.E2E_ENABLED = False
        app = _create_internal_app(
            job_scheduler=scheduler,
            schedule_reader=schedule_reader,
            executor=executor,
            settings=settings,
        )
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v1/internal/e2e/scheduler/{SCRIPT_ID}/trigger-now",
                )
        assert resp.status_code == 403
