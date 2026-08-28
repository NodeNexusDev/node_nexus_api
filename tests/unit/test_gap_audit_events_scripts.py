"""Tests for audit delete/export, SSE events, and script retry/cancel."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.audit import router as audit_router
from app.api.v1.events import _event_generator
from app.api.v1.scripts import router as scripts_router
from app.application.dto.audit import AuditLogDTO
from app.application.dto.export import AuditExportQueryDTO, AuditExportRowDTO
from app.application.ports.export import AuditExporter
from app.application.services.audit_log_service import AuditLogService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.sse_broadcaster import SseBroadcaster
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(master_key: str = "test-master") -> Any:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


def _make_log(**overrides: Any) -> AuditLogDTO:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "action": "create",
        "user": None,
        "details": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return AuditLogDTO(**defaults)


def _make_row(**overrides: Any) -> AuditExportRowDTO:
    defaults: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "action": "deploy",
        "node_id": str(uuid.uuid4()),
        "user": "admin",
        "details": "Deployed v1.0",
        "created_at": str(datetime.now(UTC)),
    }
    defaults.update(overrides)
    return AuditExportRowDTO(**defaults)


# ---------------------------------------------------------------------------
# Audit delete tests
# ---------------------------------------------------------------------------


class TestDeleteAuditLogs:
    """Tests for DELETE /api/v1/audit/ endpoint."""

    async def test_master_key_with_confirm(self) -> None:
        mock_service = AsyncMock(spec=AuditLogService)
        app = _create_audit_app(mock_service)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "master"},
            ) as ac:
                resp = await ac.delete("/api/v1/audit/?confirm=yes")
        assert resp.status_code == 204
        mock_service.delete_all_logs.assert_awaited_once()

    async def test_non_master_key(self) -> None:
        mock_service = AsyncMock(spec=AuditLogService)
        app = _create_audit_app(mock_service)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.delete("/api/v1/audit/?confirm=yes")
        assert resp.status_code == 403
        assert "Only master key" in resp.json()["detail"]

    async def test_master_key_without_confirm(self) -> None:
        mock_service = AsyncMock(spec=AuditLogService)
        app = _create_audit_app(mock_service)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "master"},
            ) as ac:
                resp = await ac.delete("/api/v1/audit/")
        assert resp.status_code == 422
        assert "confirm=yes" in resp.json()["detail"]

    async def test_non_master_without_confirm(self) -> None:
        mock_service = AsyncMock(spec=AuditLogService)
        app = _create_audit_app(mock_service)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.delete("/api/v1/audit/")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Audit export tests
# ---------------------------------------------------------------------------


class TestExportAudit:
    """Tests for GET /api/v1/audit/export endpoint."""

    async def test_csv_format(self) -> None:
        mock_exporter = AsyncMock(spec=AuditExporter)
        mock_exporter.export_audit.return_value = [_make_row(action="deploy")]
        app = _create_export_app(mock_exporter)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.get("/api/v1/audit/export?fmt=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    async def test_json_format(self) -> None:
        mock_exporter = AsyncMock(spec=AuditExporter)
        mock_exporter.export_audit.return_value = [_make_row()]
        app = _create_export_app(mock_exporter)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.get("/api/v1/audit/export?fmt=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    async def test_filters_passed_to_exporter(self) -> None:
        mock_exporter = AsyncMock(spec=AuditExporter)
        mock_exporter.export_audit.return_value = []
        app = _create_export_app(mock_exporter)
        node_id = uuid.uuid4()
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                await ac.get(
                    f"/api/v1/audit/export?fmt=json&node_id={node_id}&action=create"
                )
        call_args: AuditExportQueryDTO = mock_exporter.export_audit.call_args[0][0]
        assert call_args.action == "create"
        assert call_args.node_id == node_id

    async def test_empty_export(self) -> None:
        mock_exporter = AsyncMock(spec=AuditExporter)
        mock_exporter.export_audit.return_value = []
        app = _create_export_app(mock_exporter)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.get("/api/v1/audit/export?fmt=csv")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# SSE events tests
# ---------------------------------------------------------------------------


class TestEventGenerator:
    """Tests for _event_generator."""

    async def test_initial_keepalive(self) -> None:
        broadcaster = MagicMock(spec=SseBroadcaster)
        sub_id = "sub-1"
        queue: Any = MagicMock()

        async def _fake_get(timeout: float = 0) -> None:
            return None

        queue.get = _fake_get
        with patch("app.api.v1.events.get_sse_broadcaster", return_value=broadcaster):
            gen = _event_generator(sub_id, queue)
            first = await gen.__anext__()
            assert first == ":\n\n"

    async def test_keepalive_on_timeout(self) -> None:
        broadcaster = MagicMock(spec=SseBroadcaster)
        sub_id = "sub-1"
        queue: Any = MagicMock()
        call_count = 0

        async def _fake_get(timeout: float = 0) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                return None
            if call_count == 1:
                raise TimeoutError
            return None

        queue.get = _fake_get
        with patch("app.api.v1.events.get_sse_broadcaster", return_value=broadcaster):
            gen = _event_generator(sub_id, queue)
            first = await gen.__anext__()
            assert first == ":\n\n"
            # Timeout produces keepalive
            second = await gen.__anext__()
            assert second == ": keepalive\n\n"

    async def test_event_formatted(self) -> None:
        broadcaster = MagicMock(spec=SseBroadcaster)
        sub_id = "sub-1"
        queue: Any = MagicMock()
        call_count = 0
        mock_event = MagicMock()
        mock_event.id = "evt-1"
        mock_event.event = "node.status_changed"
        mock_event.data = {"node_id": str(uuid.uuid4()), "status": "online"}

        async def _fake_get(timeout: float = 0) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_event
            return None

        queue.get = _fake_get
        with patch("app.api.v1.events.get_sse_broadcaster", return_value=broadcaster):
            gen = _event_generator(sub_id, queue)
            await gen.__anext__()  # initial
            line = await gen.__anext__()
            assert "id: evt-1" in line
            assert "event: node.status_changed" in line
            assert "data:" in line

    async def test_none_sentinel_breaks(self) -> None:
        broadcaster = MagicMock(spec=SseBroadcaster)
        sub_id = "sub-1"
        queue: Any = MagicMock()

        async def _fake_get(timeout: float = 0) -> None:
            return None

        queue.get = _fake_get
        with patch("app.api.v1.events.get_sse_broadcaster", return_value=broadcaster):
            gen = _event_generator(sub_id, queue)
            await gen.__anext__()  # initial
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

    async def test_unsubscribe_in_finally(self) -> None:
        broadcaster = MagicMock(spec=SseBroadcaster)
        sub_id = "sub-1"
        queue: Any = MagicMock()

        async def _fake_get(timeout: float = 0) -> None:
            return None

        queue.get = _fake_get
        with patch("app.api.v1.events.get_sse_broadcaster", return_value=broadcaster):
            gen = _event_generator(sub_id, queue)
            await gen.__anext__()  # initial
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
        broadcaster.unsubscribe.assert_called_once_with(sub_id)


class TestEventStreamEndpoint:
    """Tests for GET /events/stream endpoint."""

    async def test_returns_streaming_response(self) -> None:
        from app.api.v1.events import router as events_router

        broadcaster = MagicMock(spec=SseBroadcaster)
        sub_queue: Any = AsyncMock()
        sub_queue.get = AsyncMock(return_value=None)  # sentinel → breaks loop
        broadcaster.subscribe.return_value = ("sub-1", sub_queue)
        app = FastAPI()
        app.include_router(events_router)
        with patch("app.api.v1.events.get_sse_broadcaster", return_value=broadcaster):
            mock = _mock_settings("master")
            with patch("app.api.deps.get_settings", return_value=mock):
                container = make_async_container(MockAuthServiceProvider())
                setup_dishka(container, app)
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"X-API-Key": "test-key"},
                ) as ac:
                    resp = await ac.get("/events/stream")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Script retry/cancel tests
# ---------------------------------------------------------------------------


class TestRetryScript:
    """Tests for POST /scripts/executions/{id}/retry."""

    async def test_success(self) -> None:
        mock_service = AsyncMock(spec=ExecutionLifecycleService)
        mock_service.retry_script.return_value = MagicMock(
            execution_id=str(uuid.uuid4()), status="pending"
        )
        app = _create_scripts_app(lifecycle=mock_service)
        exec_id = uuid.uuid4()
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.post(f"/api/v1/scripts/executions/{exec_id}/retry")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "Script retry scheduled" in data["message"]


class TestCancelScript:
    """Tests for POST /scripts/executions/{id}/cancel."""

    async def test_success(self) -> None:
        mock_service = AsyncMock(spec=ExecutionLifecycleService)
        app = _create_scripts_app(lifecycle=mock_service)
        exec_id = uuid.uuid4()
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.post(f"/api/v1/scripts/executions/{exec_id}/cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["execution_id"] == str(exec_id)
        mock_service.cancel_execution.assert_awaited_once()


class TestGetScriptStats:
    """Tests for GET /scripts/{script_id}/stats."""

    async def test_success(self) -> None:
        from app.application.dto.execution_stats import ExecutionStatsDTO

        mock_stats = AsyncMock(spec=ExecutionStatsService)
        mock_stats.get_script_stats.return_value = ExecutionStatsDTO(
            total=10,
            successful=8,
            failed=2,
            success_rate=0.8,
            avg_duration_ms=1500.0,
            min_duration_ms=100.0,
            max_duration_ms=3000.0,
            last_executed_at=datetime.now(UTC),
        )
        app = _create_scripts_app(stats=mock_stats)
        script_id = uuid.uuid4()
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.get(f"/api/v1/scripts/{script_id}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert data["successful"] == 8
        assert data["success_rate"] == 0.8


class TestScheduledExecutionHistory:
    """Tests for GET /scripts/{script_id}/schedule/history."""

    async def test_returns_paginated_history(self) -> None:
        from datetime import UTC, datetime

        exec_id = uuid.uuid4()
        script_id = uuid.uuid4()
        node_id = uuid.uuid4()

        mock_execution = MagicMock()
        mock_execution.id = exec_id
        mock_execution.script_id = script_id
        mock_execution.node_id = node_id
        mock_execution.status = "success"
        mock_execution.exit_code = 0
        mock_execution.started_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_execution.finished_at = datetime(2025, 1, 1, 0, 1, tzinfo=UTC)
        mock_execution.trigger = "scheduled"
        mock_execution.error_message = None

        mock_history = AsyncMock(spec=ScriptHistoryService)
        mock_history.get_executions.return_value = ([mock_execution], 1)
        app = _create_scripts_app(history=mock_history)
        with patch("app.api.deps.get_settings", return_value=_mock_settings("master")):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-key"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v1/scripts/{script_id}/schedule/history?page=1&size=10"
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        mock_history.get_executions.assert_awaited_once_with(
            script_id, page=1, size=10, trigger="scheduled"
        )


# ---------------------------------------------------------------------------
# Helpers – app factories
# ---------------------------------------------------------------------------


def _create_audit_app(service: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(audit_router, prefix="/api/v1")

    class P(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> AuditLogService:
            return as_typed_mock(AuditLogService, service)

    container = make_async_container(P(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


def _create_export_app(exporter: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(audit_router, prefix="/api/v1")

    class P(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> AuditLogService:
            return as_typed_mock(AuditLogService, AsyncMock(spec=AuditLogService))

        @provide(scope=Scope.REQUEST)
        def get_exporter(self) -> AuditExporter:
            return exporter

    container = make_async_container(P(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


def _create_scripts_app(
    *,
    lifecycle: AsyncMock | None = None,
    stats: AsyncMock | None = None,
    history: AsyncMock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(scripts_router, prefix="/api/v1")

    class P(Provider):
        @provide(scope=Scope.REQUEST)
        def get_lifecycle(self) -> ExecutionLifecycleService:
            return as_typed_mock(
                ExecutionLifecycleService,
                lifecycle
                if lifecycle is not None
                else AsyncMock(spec=ExecutionLifecycleService),
            )

        @provide(scope=Scope.REQUEST)
        def get_stats(self) -> ExecutionStatsService:
            return as_typed_mock(
                ExecutionStatsService,
                stats if stats is not None else AsyncMock(spec=ExecutionStatsService),
            )

        @provide(scope=Scope.REQUEST)
        def get_history(self) -> ScriptHistoryService:
            return as_typed_mock(
                ScriptHistoryService,
                history
                if history is not None
                else AsyncMock(spec=ScriptHistoryService),
            )

    container = make_async_container(P(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app
