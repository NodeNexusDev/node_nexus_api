"""Unit tests for scripts API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.scripts import router as scripts_router
from app.api.v1.scripts_bulk import router as scripts_bulk_router
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.schedule_management import ScheduleManagementService
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.script_management_service import ScriptManagementService
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_scripts_app(**services: object) -> FastAPI:
    app = FastAPI()
    app.include_router(scripts_router, prefix="/api/v1")
    app.include_router(scripts_bulk_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_script_management(self) -> ScriptManagementService:
            return as_typed_mock(
                ScriptManagementService,
                services.get("script_management", AsyncMock()),
            )

        @provide(scope=Scope.REQUEST)
        def get_script_execution(self) -> ScriptExecutionService:
            return as_typed_mock(
                ScriptExecutionService, services.get("script_execution", AsyncMock())
            )

        @provide(scope=Scope.REQUEST)
        def get_script_history(self) -> ScriptHistoryService:
            return as_typed_mock(
                ScriptHistoryService, services.get("script_history", AsyncMock())
            )

        @provide(scope=Scope.REQUEST)
        def get_execution_lifecycle(self) -> ExecutionLifecycleService:
            return as_typed_mock(
                ExecutionLifecycleService,
                services.get("execution_lifecycle", AsyncMock()),
            )

        @provide(scope=Scope.REQUEST)
        def get_execution_stats(self) -> ExecutionStatsService:
            return as_typed_mock(
                ExecutionStatsService, services.get("execution_stats", AsyncMock())
            )

        @provide(scope=Scope.REQUEST)
        def get_schedule_management(self) -> ScheduleManagementService:
            return as_typed_mock(
                ScheduleManagementService,
                services.get("schedule_management", AsyncMock()),
            )

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


SCRIPT_ID = "00000000-0000-0000-0000-000000000001"
EXEC_ID = "00000000-0000-0000-0000-000000000002"

_settings_patcher = patch(
    "app.api.deps.get_settings",
    return_value=_mock_settings("test-master"),
)


# ── bulk/retry ──


class TestBulkRetryScripts:
    @pytest.mark.asyncio
    async def test_bulk_retry_scripts(self) -> None:
        svc = AsyncMock()
        svc.retry_script.return_value = MagicMock(
            execution_id=EXEC_ID,
            status="retry_scheduled",
        )
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/scripts/bulk/retry",
                    json={"execution_ids": [EXEC_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1


# ── bulk/cancel ──


class TestBulkCancelScripts:
    @pytest.mark.asyncio
    async def test_bulk_cancel_scripts(self) -> None:
        svc = AsyncMock()
        svc.cancel_execution = AsyncMock()
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/scripts/bulk/cancel",
                    json={"execution_ids": [EXEC_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1


# ── single retry ──


class TestRetryScript:
    @pytest.mark.asyncio
    async def test_retry_single_script(self) -> None:
        svc = AsyncMock()
        svc.retry_script.return_value = MagicMock(
            execution_id=EXEC_ID,
            status="retry_scheduled",
        )
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v1/scripts/executions/{EXEC_ID}/retry",
                )
        assert resp.status_code == 200


# ── single cancel ──


class TestCancelScript:
    @pytest.mark.asyncio
    async def test_cancel_single_script(self) -> None:
        svc = AsyncMock()
        svc.cancel_execution = AsyncMock()
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v1/scripts/executions/{EXEC_ID}/cancel",
                )
        assert resp.status_code == 200


# ── script stats ──


class TestScriptStats:
    @pytest.mark.asyncio
    async def test_get_script_stats(self) -> None:
        svc = AsyncMock()
        svc.get_stats.return_value = MagicMock(
            total_executions=10, successful=8, failed=2
        )
        app = _create_scripts_app(execution_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v1/scripts/{SCRIPT_ID}/stats",
                )
        assert resp.status_code == 200


# ── script executions list ──


class TestScriptExecutions:
    @pytest.mark.asyncio
    async def test_get_script_executions(self) -> None:
        svc = AsyncMock()
        svc.get_executions.return_value = ([], 0)
        app = _create_scripts_app(script_history=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v1/scripts/{SCRIPT_ID}/executions",
                )
        assert resp.status_code == 200


# ── script schedule/history ──


class TestScriptScheduleHistory:
    @pytest.mark.asyncio
    async def test_get_script_schedule_history(self) -> None:
        svc = AsyncMock()
        svc.get_executions.return_value = ([], 0)
        app = _create_scripts_app(script_history=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v1/scripts/{SCRIPT_ID}/schedule/history",
                )
        assert resp.status_code == 200


# ── empty bulk retry (no execution_ids) ──


class TestBulkRetryEmpty:
    @pytest.mark.asyncio
    async def test_bulk_retry_empty(self) -> None:
        svc = AsyncMock()
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/scripts/bulk/retry",
                    json={"execution_ids": []},
                )
        assert resp.status_code == 422


class TestBulkCancelEmpty:
    @pytest.mark.asyncio
    async def test_bulk_cancel_empty(self) -> None:
        svc = AsyncMock()
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/scripts/bulk/cancel",
                    json={"execution_ids": []},
                )
        assert resp.status_code == 422


class TestBulkRetryException:
    @pytest.mark.asyncio
    async def test_bulk_retry_exception(self) -> None:
        svc = AsyncMock()
        svc.retry_script.side_effect = RuntimeError("retry failed")
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/scripts/bulk/retry",
                    json={"execution_ids": [EXEC_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["failed"] == 1


class TestBulkCancelException:
    @pytest.mark.asyncio
    async def test_bulk_cancel_exception(self) -> None:
        svc = AsyncMock()
        svc.cancel_execution.side_effect = RuntimeError("cancel failed")
        app = _create_scripts_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/scripts/bulk/cancel",
                    json={"execution_ids": [EXEC_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["failed"] == 1
