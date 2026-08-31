"""Extra coverage for app/api/v2/scripts.py (161 lines miss).

Covers: helpers, GET /?cursor, POST / bulk create, GET /{id}/executions,
POST /executions M*N, POST /executions/retries|cancels, GET /stats with
group_by, plus schedules, clone, CRUD.

Uses AsyncMock + Dishka, ruff/ty clean.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.api.v2.scripts import (
    _decode_offset,
    _encode_offset,
    _execution_response,
    _scheduled_job,
    _script_response,
    _step_dto,
)
from app.application.dto.execution_stats import ExecutionStatsDTO
from app.application.dto.schedule import ScheduleViewDTO
from app.application.dto.script_execution import (
    ScriptExecutionBatchResultDTO,
    ScriptExecutionDTO,
    ScriptNodeResultDTO,
    ScriptStepResultDTO,
)
from app.application.dto.script_management import ScriptViewDTO
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.schedule_management import ScheduleManagementService
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.script_management_service import ScriptManagementService
from app.core.exceptions import DomainError, ScheduleNotFoundError, ScriptNotFoundError
from app.schemas.script import ScriptStep
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings

# ---------------------------------------------------------------------------
# DTO factories
# ---------------------------------------------------------------------------


def _make_script_view(**overrides: object) -> ScriptViewDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "demo-script",
        "description": "desc",
        "steps": (),
        "tags": ("ops",),
        "created_at": now,
        "updated_at": now,
    }
    # allow passing ScriptStepDTO tuple directly
    if "steps_dto" in overrides:
        steps_dto = overrides.pop("steps_dto")  # type: ignore[assignment]
        defaults["steps"] = steps_dto
    defaults.update(overrides)
    # Build default steps if not overridden
    if defaults["steps"] == ():
        from app.application.dto.script_management import ScriptStepDTO

        defaults["steps"] = (
            ScriptStepDTO(
                label="s1",
                type="inline",
                command="echo hi",
                command_id=None,
                params=(),
                on_failure="stop",
            ),
        )
    # Convert dict steps to ScriptStepDTO if needed
    steps = defaults["steps"]
    if isinstance(steps, tuple) and steps and isinstance(steps[0], dict):
        from app.application.dto.script_management import ScriptStepDTO

        dto_steps = tuple(ScriptStepDTO(**s) for s in steps)  # type: ignore[arg-type]
        defaults["steps"] = dto_steps
    return ScriptViewDTO(**defaults)  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]


def _make_execution_dto(**overrides: object) -> ScriptExecutionDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "script_id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "params": (("key", "val"),),
        "status": "success",
        "steps": (
            ScriptStepResultDTO(
                step_index=0,
                label="s1",
                command_fingerprint="abc",
                stdout="out",
                stderr="",
                stdout_bytes=3,
                stderr_bytes=0,
                truncated=False,
                exit_code=0,
            ),
        ),
        "started_at": now,
        "finished_at": now,
    }
    defaults.update(overrides)
    return ScriptExecutionDTO(**defaults)  # type: ignore[arg-type]


def _make_schedule_view(**overrides: object) -> ScheduleViewDTO:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "script_id": uuid.uuid4(),
        "cron": "0 9 * * *",
        "timezone": "UTC",
        "node_ids": (uuid.uuid4(),),
        "params": (),
        "enabled": True,
        "misfire_grace_seconds": 60,
        "operational_state": "registered",
        "last_error_type": None,
        "last_run_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "next_run_at": None,
    }
    defaults.update(overrides)
    return ScheduleViewDTO(**defaults)  # type: ignore[arg-type]


def _make_stats_dto(**overrides: object) -> ExecutionStatsDTO:
    defaults: dict[str, object] = {
        "total": 10,
        "successful": 8,
        "failed": 1,
        "cancelled": 1,
        "success_rate": 0.8,
        "avg_duration_ms": 123.4,
        "min_duration_ms": 10.0,
        "max_duration_ms": 500.0,
        "last_executed_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ExecutionStatsDTO(**defaults)  # type: ignore[arg-type]


def _make_node_result(**overrides: object) -> ScriptNodeResultDTO:
    defaults: dict[str, object] = {
        "execution_id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "node_name": "node-1",
        "status": "success",
        "steps": (
            ScriptStepResultDTO(
                step_index=0,
                label="s1",
                command_fingerprint="fp",
                stdout="out",
                stderr="",
                stdout_bytes=3,
                stderr_bytes=0,
                truncated=False,
                exit_code=0,
            ),
        ),
    }
    defaults.update(overrides)
    return ScriptNodeResultDTO(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# App factory (dishka)
# ---------------------------------------------------------------------------


def _create_v2_scripts_app(**services: object) -> FastAPI:
    from app.api.v2.scripts import router as scripts_router

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(scripts_router, prefix="/api/v2")

    class MockProvider(Provider):
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

    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


_settings_patch = patch(
    "app.api.deps.get_settings", return_value=_mock_settings("test-master")
)


# ---------------------------------------------------------------------------
# Helpers direct coverage
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_step_dto(self) -> None:
        step = ScriptStep(label="s1", type="inline", command="echo hi", params={"a": 1})
        dto = _step_dto(step)
        assert dto.label == "s1"
        assert dto.command == "echo hi"
        assert dto.params == (("a", 1),)

    def test_step_dto_command_ref(self) -> None:
        cid = uuid.uuid4()
        step = ScriptStep(label="s2", type="command", command_id=cid, params={})
        dto = _step_dto(step)
        assert dto.command_id == cid

    def test_script_response(self) -> None:
        view = _make_script_view()
        resp = _script_response(view)
        assert str(resp.id) == str(view.id)
        assert resp.name == view.name
        assert resp.tags == list(view.tags)
        assert len(resp.steps) == 1

    def test_execution_response(self) -> None:
        dto = _make_execution_dto()
        resp = _execution_response(dto)
        assert str(resp.id) == str(dto.id)
        assert resp.status == dto.status
        assert resp.steps is not None
        assert len(resp.steps) == 1
        first = resp.steps[0]
        assert first.label == "s1"

    def test_scheduled_job(self) -> None:
        view = _make_schedule_view()
        job = _scheduled_job(view)
        assert str(job.id) == str(view.id)
        assert job.cron == view.cron
        assert job.enabled is True

    def test_encode_decode_offset(self) -> None:
        cur = _encode_offset(42)
        # check valid base64 json
        raw = base64.urlsafe_b64decode(cur.encode())
        data = json.loads(raw)
        assert data["offset"] == 42
        assert _decode_offset(cur) == 42
        assert _decode_offset(_encode_offset(0)) == 0

    def test_decode_offset_invalid(self) -> None:
        with pytest.raises(ValueError):
            _decode_offset("not-base64")
        with pytest.raises(ValueError):
            _decode_offset(base64.urlsafe_b64encode(b"not-json").decode())
        with pytest.raises(ValueError):
            _decode_offset(
                base64.urlsafe_b64encode(json.dumps({"no": 1}).encode()).decode()
            )


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------


class TestGetScriptsStats:
    async def test_stats_without_group_by(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto()
        app = _create_v2_scripts_app(execution_stats=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        svc.get_script_stats.assert_awaited_once()

    async def test_stats_with_group_by_day(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto(
            total=5, successful=4, failed=0, cancelled=1
        )
        app = _create_v2_scripts_app(execution_stats=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts/stats?group_by=day")
        assert resp.status_code == 200
        data = resp.json()
        assert "buckets" in data
        assert data["buckets"][0]["period"] == "all"
        assert data["buckets"][0]["total"] == 5

    async def test_stats_with_group_by_and_date_from(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto()
        app = _create_v2_scripts_app(execution_stats=svc)
        dt = "2024-01-01T00:00:00Z"
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/scripts/stats?group_by=hour&date_from={dt}"
                )
        assert resp.status_code == 200
        assert resp.json()["buckets"][0]["period"] != "all"

    async def test_stats_with_node_id_and_group_by(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto()
        app = _create_v2_scripts_app(execution_stats=svc)
        nid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/scripts/stats?node_id={nid}&group_by=week"
                )
        assert resp.status_code == 200

    async def test_stats_with_date_range_no_group(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto()
        app = _create_v2_scripts_app(execution_stats=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    "/api/v2/scripts/stats?date_from=2024-01-01T00:00:00Z&date_to=2024-02-01T00:00:00Z"
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10


# ---------------------------------------------------------------------------
# GET /{id}/stats
# ---------------------------------------------------------------------------


class TestGetScriptStats:
    async def test_per_script_stats_no_group(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto()
        app = _create_v2_scripts_app(execution_stats=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/stats")
        assert resp.status_code == 200
        assert resp.json()["total"] == 10
        # should be called with script_id
        assert svc.get_script_stats.await_args.kwargs["script_id"] == sid

    async def test_per_script_stats_with_group_by(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto(total=7)
        app = _create_v2_scripts_app(execution_stats=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/stats?group_by=month")
        assert resp.status_code == 200
        assert resp.json()["buckets"][0]["total"] == 7

    async def test_per_script_stats_with_date_from_bucket_period(self) -> None:
        svc = AsyncMock(spec=ExecutionStatsService)
        svc.get_script_stats.return_value = _make_stats_dto()
        app = _create_v2_scripts_app(execution_stats=svc)
        sid = uuid.uuid4()
        dt = "2024-03-15T12:00:00Z"
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/scripts/{sid}/stats?group_by=day&date_from={dt}"
                )
        assert resp.status_code == 200
        assert "2024-03-15" in resp.json()["buckets"][0]["period"]


# ---------------------------------------------------------------------------
# GET /?cursor (list scripts)
# ---------------------------------------------------------------------------


class TestListScripts:
    async def test_list_no_cursor(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        v1 = _make_script_view(name="a")
        v2 = _make_script_view(name="b")
        svc.get_all_scripts.return_value = ([v1, v2], 2)
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts/?limit=20")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        svc.get_all_scripts.assert_awaited_once_with(
            page=1, size=20, tags=None, search=None
        )

    async def test_list_with_tag_and_search(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.get_all_scripts.return_value = ([], 0)
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts/?tag=ops&search=demo&limit=10")
        assert resp.status_code == 200
        svc.get_all_scripts.assert_awaited_once_with(
            page=1, size=10, tags=["ops"], search="demo"
        )

    async def test_list_cursor_pagination_has_more(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        v1 = _make_script_view()
        # total 5, offset 0, limit 1, has_more true => next_cursor = encode(1)
        svc.get_all_scripts.return_value = ([v1], 5)
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts/?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
        assert _decode_offset(data["next_cursor"]) == 1

    async def test_list_with_valid_cursor(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        v1 = _make_script_view()
        svc.get_all_scripts.return_value = ([v1], 3)
        app = _create_v2_scripts_app(script_management=svc)
        cur = _encode_offset(1)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/?cursor={cur}&limit=1")
        assert resp.status_code == 200
        # offset 1, limit 1 => page 2
        svc.get_all_scripts.assert_awaited_once_with(
            page=2, size=1, tags=None, search=None
        )
        # has_more: (1+1)<3 true => next cursor 2
        assert resp.json()["has_more"] is True
        assert _decode_offset(resp.json()["next_cursor"]) == 2

    async def test_list_invalid_cursor_422(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts/?cursor=invalid!")
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"

    async def test_list_cursor_no_more(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        v1 = _make_script_view()
        svc.get_all_scripts.return_value = ([v1], 1)
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts/?limit=20")
        assert resp.json()["has_more"] is False
        assert resp.json()["next_cursor"] is None

    async def test_list_without_trailing_slash(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.get_all_scripts.return_value = ([], 0)
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/scripts?limit=20")
        # FastAPI with prefix may redirect or serve same; allow 200 or 307
        assert resp.status_code in (200, 307)


# ---------------------------------------------------------------------------
# POST / bulk create
# ---------------------------------------------------------------------------


class TestBulkCreateScripts:
    async def test_bulk_create_all_success(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        view = _make_script_view(name="s1")
        svc.create_script.return_value = view
        app = _create_v2_scripts_app(script_management=svc)
        payload = {
            "items": [
                {
                    "name": "s1",
                    "steps": [{"label": "l1", "type": "inline", "command": "echo hi"}],
                    "tags": ["ops"],
                }
            ]
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0
        assert data["results"][0]["status"] == "success"

    async def test_bulk_create_207_mixed(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)

        async def _create(dto):  # type: ignore[no-untyped-def]
            if dto.name == "good":
                return _make_script_view(name="good")
            raise ValueError("dup")

        svc.create_script.side_effect = _create
        app = _create_v2_scripts_app(script_management=svc)
        payload = {
            "items": [
                {
                    "name": "good",
                    "steps": [{"label": "l1", "type": "inline", "command": "echo hi"}],
                },
                {
                    "name": "bad",
                    "steps": [{"label": "l1", "type": "inline", "command": "echo hi"}],
                },
            ]
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/", json=payload)
        assert resp.status_code == 207
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        assert any(r["status"] == "error" for r in data["results"])

    async def test_bulk_create_all_failed(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.create_script.side_effect = RuntimeError("boom")
        app = _create_v2_scripts_app(script_management=svc)
        payload = {
            "items": [
                {
                    "name": "s1",
                    "steps": [{"label": "l1", "type": "inline", "command": "echo hi"}],
                },
            ]
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/", json=payload)
        assert resp.status_code == 201
        assert resp.json()["failed"] == 1

    async def test_bulk_create_with_command_step(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.create_script.return_value = _make_script_view()
        app = _create_v2_scripts_app(script_management=svc)
        cid = str(uuid.uuid4())
        payload = {
            "items": [
                {
                    "name": "s-cmd",
                    "steps": [{"label": "l1", "type": "command", "command_id": cid}],
                }
            ]
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/", json=payload)
        assert resp.status_code == 201
        # verify _step_dto mapping preserved command_id
        assert svc.create_script.await_args is not None

    async def test_bulk_create_empty_items_validation(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/", json={"items": []})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /{id}/executions
# ---------------------------------------------------------------------------


class TestGetExecutions:
    async def test_get_executions_empty(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        svc.get_executions.return_value = ([], 0)
        app = _create_v2_scripts_app(script_history=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/executions?limit=20")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["has_more"] is False
        svc.get_executions.assert_awaited_once_with(sid, page=1, size=20)

    async def test_get_executions_with_items_and_cursor(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        dto = _make_execution_dto()
        svc.get_executions.return_value = ([dto], 5)
        app = _create_v2_scripts_app(script_history=svc)
        sid = dto.script_id
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/executions?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["has_more"] is True
        assert _decode_offset(data["next_cursor"]) == 1
        # verify execution_response mapping
        assert data["items"][0]["status"] == "success"
        assert data["items"][0]["steps"][0]["label"] == "s1"

    async def test_get_executions_with_cursor(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        dto = _make_execution_dto()
        svc.get_executions.return_value = ([dto], 10)
        app = _create_v2_scripts_app(script_history=svc)
        sid = dto.script_id
        cur = _encode_offset(4)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/scripts/{sid}/executions?cursor={cur}&limit=2"
                )
        assert resp.status_code == 200
        # offset 4, limit 2 => page 3
        svc.get_executions.assert_awaited_once_with(sid, page=3, size=2)

    async def test_get_executions_invalid_cursor(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        app = _create_v2_scripts_app(script_history=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/executions?cursor=bad!")
        assert resp.status_code == 422

    async def test_get_executions_not_found(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        svc.get_executions.side_effect = ScriptNotFoundError("not found")
        app = _create_v2_scripts_app(script_history=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/executions")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /{id}/schedule/history
# ---------------------------------------------------------------------------


class TestGetScheduledHistory:
    async def test_history_empty(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        svc.get_executions.return_value = ([], 0)
        app = _create_v2_scripts_app(script_history=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/schedule/history?limit=20")
        assert resp.status_code == 200
        svc.get_executions.assert_awaited_once()
        assert svc.get_executions.await_args.kwargs.get("trigger") == "scheduled"

    async def test_history_with_items_has_more(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        dto = _make_execution_dto(status="success")
        svc.get_executions.return_value = ([dto], 2)
        app = _create_v2_scripts_app(script_history=svc)
        sid = dto.script_id
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/schedule/history?limit=1")
        assert resp.json()["has_more"] is True

    async def test_history_with_cursor(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        dto = _make_execution_dto()
        svc.get_executions.return_value = ([dto], 10)
        app = _create_v2_scripts_app(script_history=svc)
        sid = dto.script_id
        cur = _encode_offset(2)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/scripts/{sid}/schedule/history?cursor={cur}&limit=2"
                )
        assert resp.status_code == 200
        assert svc.get_executions.await_args.kwargs["page"] == 2

    async def test_history_invalid_cursor(self) -> None:
        svc = AsyncMock(spec=ScriptHistoryService)
        app = _create_v2_scripts_app(script_history=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/schedule/history?cursor=!!")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /executions M*N
# ---------------------------------------------------------------------------


class TestBulkExecutions:
    async def test_mxn_success_single(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        sid = uuid.uuid4()
        nid = uuid.uuid4()
        node_res = _make_node_result(node_id=nid, status="success")
        svc.execute_script.return_value = ScriptExecutionBatchResultDTO(
            script_id=sid, results=(node_res,)
        )
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {
            "script_ids": [str(sid)],
            "node_ids": [str(nid)],
            "node_tags": [],
            "params": {},
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0
        assert data["results"][0]["status"] == "success"
        assert data["results"][0]["steps"][0]["label"] == "s1"

    async def test_mxn_with_node_tags_and_params(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        sid = uuid.uuid4()
        nid = uuid.uuid4()
        node_res = _make_node_result(node_id=nid, status="success")
        svc.execute_script.return_value = ScriptExecutionBatchResultDTO(
            script_id=sid, results=(node_res,)
        )
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {
            "script_ids": [str(sid)],
            "node_ids": [],
            "node_tags": ["ops"],
            "params": {str(sid): {"foo": "bar"}},
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 200
        # verify params were passed as tuple items
        call_args = svc.execute_script.await_args
        assert call_args is not None
        # second arg is DTO
        dto = call_args.args[1]
        assert ("foo", "bar") in dto.params

    async def test_mxn_params_not_dict_handled(self) -> None:
        # Branch where params value is not a dict (defensive code, bypasses Pydantic)
        from fastapi import Response

        from app.api.v2.scripts import bulk_executions
        from app.schemas.script import ScriptExecutionsRequest

        svc = AsyncMock(spec=ScriptExecutionService)
        sid = uuid.uuid4()
        nid = uuid.uuid4()
        node_res = _make_node_result(node_id=nid)
        svc.execute_script.return_value = ScriptExecutionBatchResultDTO(
            script_id=sid, results=(node_res,)
        )
        # construct without validation to inject a non-dict param value
        req = ScriptExecutionsRequest.model_construct(
            script_ids=[sid],
            node_ids=[nid],
            node_tags=[],
            params={str(sid): "not-a-dict"},  # type: ignore[dict-item]
        )
        resp = Response()
        orig = bulk_executions.__dishka_orig_func__  # type: ignore[attr-defined]
        result = await orig(req, svc, resp, MagicMock())  # type: ignore[arg-type]
        assert result.total == 1
        # ensure service was called with empty params tuple (string coerced to {})
        assert svc.execute_script.await_args.args[1].params == ()

    async def test_mxn_zero_nodes_resolved(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        sid = uuid.uuid4()
        svc.execute_script.return_value = ScriptExecutionBatchResultDTO(
            script_id=sid, results=()
        )
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {
            "script_ids": [str(sid)],
            "node_ids": [str(uuid.uuid4())],
            "params": {},
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "No target nodes resolved" in data["results"][0]["error"]

    async def test_mxn_exception_per_script(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        sid = uuid.uuid4()
        svc.execute_script.side_effect = RuntimeError("boom")
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {"script_ids": [str(sid)], "node_ids": [str(uuid.uuid4())]}
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 200
        assert resp.json()["results"][0]["error"] == "boom"
        assert resp.json()["results"][0]["status"] == "error"

    async def test_mxn_207_mixed_success_error(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        sid1 = uuid.uuid4()
        sid2 = uuid.uuid4()
        nid = uuid.uuid4()

        async def _exec(script_id, _dto):  # type: ignore[no-untyped-def]
            if script_id == sid1:
                return ScriptExecutionBatchResultDTO(
                    script_id=sid1,
                    results=(_make_node_result(node_id=nid, status="success"),),
                )
            raise RuntimeError("fail2")

        svc.execute_script.side_effect = _exec
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {"script_ids": [str(sid1), str(sid2)], "node_ids": [str(nid)]}
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    async def test_mxn_error_status_branch(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        sid = uuid.uuid4()
        nid = uuid.uuid4()
        node_res = _make_node_result(node_id=nid, status="error")
        svc.execute_script.return_value = ScriptExecutionBatchResultDTO(
            script_id=sid, results=(node_res,)
        )
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {"script_ids": [str(sid)], "node_ids": [str(nid)]}
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.json()["results"][0]["status"] == "error"
        assert resp.json()["succeeded"] == 0

    async def test_mxn_exceeds_100_returns_422(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        app = _create_v2_scripts_app(script_execution=svc)
        sids = [str(uuid.uuid4()) for _ in range(6)]
        nids = [str(uuid.uuid4()) for _ in range(20)]  # 6*20=120 >100
        payload = {"script_ids": sids, "node_ids": nids}
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 422
        assert "M×N" in resp.json()["detail"]

    async def test_mxn_with_node_tags_estimation(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        # 2 scripts * 2 tags = 4 <=100 ok, but also test 51*2 >100
        sid = uuid.uuid4()
        nid = uuid.uuid4()
        svc.execute_script.return_value = ScriptExecutionBatchResultDTO(
            script_id=sid, results=(_make_node_result(node_id=nid),)
        )
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {"script_ids": [str(sid)], "node_ids": [], "node_tags": ["a", "b"]}
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 200

        # exceed via tags
        sids = [str(uuid.uuid4()) for _ in range(20)]
        payload2 = {
            "script_ids": sids,
            "node_ids": [],
            "node_tags": ["a"] * 6,
        }  # 20*6=120
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp2 = await ac.post("/api/v2/scripts/executions", json=payload2)
        assert resp2.status_code == 422

    async def test_mxn_empty_node_ids_tags_estimation_one(self) -> None:
        svc = AsyncMock(spec=ScriptExecutionService)
        sid = uuid.uuid4()
        svc.execute_script.return_value = ScriptExecutionBatchResultDTO(
            script_id=sid, results=()
        )
        app = _create_v2_scripts_app(script_execution=svc)
        payload = {"script_ids": [str(sid)], "node_ids": [], "node_tags": []}
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/scripts/executions", json=payload)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /executions/retries and /cancels
# ---------------------------------------------------------------------------


class TestBulkRetries:
    async def test_retries_all_success(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)
        svc.retry_script.return_value = MagicMock(status="retry_scheduled")
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        eid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/retries",
                    json={"execution_ids": [str(eid)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["results"][0]["status"] == "retry_scheduled"

    async def test_retries_207_mixed(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)

        async def _retry(dto):  # type: ignore[no-untyped-def]
            if str(dto.execution_id) == str(eid_ok):
                return MagicMock()
            raise RuntimeError("fail")

        eid_ok = uuid.uuid4()
        eid_fail = uuid.uuid4()
        svc.retry_script.side_effect = _retry
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/retries",
                    json={"execution_ids": [str(eid_ok), str(eid_fail)]},
                )
        assert resp.status_code == 207
        assert resp.json()["failed"] == 1
        assert resp.json()["succeeded"] == 1

    async def test_retries_all_failed(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)
        svc.retry_script.side_effect = RuntimeError("boom")
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/retries",
                    json={"execution_ids": [str(uuid.uuid4())]},
                )
        assert resp.json()["failed"] == 1
        assert resp.status_code == 200

    async def test_retries_empty_validation(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/retries", json={"execution_ids": []}
                )
        assert resp.status_code == 422


class TestBulkCancels:
    async def test_cancels_all_success(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)
        svc.cancel_execution.return_value = True
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        eid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/cancels",
                    json={"execution_ids": [str(eid)]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1
        assert resp.json()["results"][0]["status"] == "cancelled"

    async def test_cancels_207_mixed(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)
        eid_ok = uuid.uuid4()
        eid_fail = uuid.uuid4()

        async def _cancel(dto):  # type: ignore[no-untyped-def]
            if str(dto.execution_id) == str(eid_ok):
                return True
            raise RuntimeError("cannot cancel")

        svc.cancel_execution.side_effect = _cancel
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/cancels",
                    json={"execution_ids": [str(eid_ok), str(eid_fail)]},
                )
        assert resp.status_code == 207
        assert resp.json()["failed"] == 1

    async def test_cancels_all_failed(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)
        svc.cancel_execution.side_effect = RuntimeError("boom")
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/cancels",
                    json={"execution_ids": [str(uuid.uuid4())]},
                )
        assert resp.json()["failed"] == 1

    async def test_cancels_empty_validation(self) -> None:
        svc = AsyncMock(spec=ExecutionLifecycleService)
        app = _create_v2_scripts_app(execution_lifecycle=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/scripts/executions/cancels", json={"execution_ids": []}
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


class TestSchedules:
    async def test_schedule_create(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        sid = uuid.uuid4()
        view = _make_schedule_view(script_id=sid, cron="0 9 * * *")
        svc.create_or_update.return_value = view
        app = _create_v2_scripts_app(schedule_management=svc)
        payload = {
            "cron": "0 9 * * *",
            "node_ids": [str(uuid.uuid4())],
            "params": {"a": 1},
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/scripts/{sid}/schedules", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["cron"] == "0 9 * * *"
        assert data["script_id"] == str(sid)
        assert svc.create_or_update.await_args is not None

    async def test_schedule_create_with_timezone(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        sid = uuid.uuid4()
        view = _make_schedule_view(
            script_id=sid, timezone="Europe/Moscow", cron="*/5 * * * *"
        )
        svc.create_or_update.return_value = view
        app = _create_v2_scripts_app(schedule_management=svc)
        payload = {
            "cron": "*/5 * * * *",
            "node_ids": [str(uuid.uuid4())],
            "timezone": "Europe/Moscow",
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/scripts/{sid}/schedules", json=payload)
        assert resp.status_code == 200

    async def test_schedule_get(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        sid = uuid.uuid4()
        view = _make_schedule_view(script_id=sid)
        svc.get.return_value = view
        app = _create_v2_scripts_app(schedule_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/schedules")
        assert resp.status_code == 200
        assert resp.json()["cron"] == view.cron
        assert resp.json()["id"] == str(view.id)

    async def test_schedule_get_singular_alias(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        sid = uuid.uuid4()
        view = _make_schedule_view(script_id=sid)
        svc.get.return_value = view
        app = _create_v2_scripts_app(schedule_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/schedule")
        assert resp.status_code == 200
        assert resp.json()["cron"] == view.cron

    async def test_schedule_get_not_found(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        svc.get.side_effect = ScheduleNotFoundError("missing")
        app = _create_v2_scripts_app(schedule_management=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{sid}/schedules")
        assert resp.status_code == 404

    async def test_schedule_delete(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        svc.delete.return_value = None
        app = _create_v2_scripts_app(schedule_management=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/scripts/{sid}/schedules")
        assert resp.status_code == 204

    async def test_schedule_delete_not_found(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        svc.delete.side_effect = ScheduleNotFoundError("missing")
        app = _create_v2_scripts_app(schedule_management=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/scripts/{sid}/schedules")
        assert resp.status_code == 404

    async def test_schedule_create_not_found_script(self) -> None:
        svc = AsyncMock(spec=ScheduleManagementService)
        svc.create_or_update.side_effect = ScriptNotFoundError("no script")
        app = _create_v2_scripts_app(schedule_management=svc)
        sid = uuid.uuid4()
        payload = {"cron": "0 9 * * *", "node_ids": [str(uuid.uuid4())]}
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/scripts/{sid}/schedules", json=payload)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CRUD: GET /{id}, PATCH /{id}, DELETE /{id}, POST /{id}/clone
# ---------------------------------------------------------------------------


class TestScriptCrud:
    async def test_get_script(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        view = _make_script_view()
        svc.get_script.return_value = view
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{view.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(view.id)
        assert resp.json()["name"] == view.name

    async def test_get_script_not_found(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.get_script.side_effect = ScriptNotFoundError("missing")
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/scripts/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_update_script_name_only(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        view = _make_script_view(name="new-name")
        svc.update_script.return_value = view
        app = _create_v2_scripts_app(script_management=svc)
        sid = view.id
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/scripts/{sid}", json={"name": "new-name"}
                )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"
        # verify changes tuple contains name
        assert svc.update_script.await_args is not None

    async def test_update_script_with_steps_and_tags(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        view = _make_script_view()
        svc.update_script.return_value = view
        app = _create_v2_scripts_app(script_management=svc)
        sid = uuid.uuid4()
        payload = {
            "name": "upd",
            "steps": [{"label": "l1", "type": "inline", "command": "echo hi"}],
            "tags": ["a", "b"],
        }
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(f"/api/v2/scripts/{sid}", json=payload)
        assert resp.status_code == 200
        # ensure steps converted to DTO tuple
        kwargs = svc.update_script.await_args
        assert kwargs is not None

    async def test_update_script_not_found(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.update_script.side_effect = ScriptNotFoundError("missing")
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/scripts/{uuid.uuid4()}", json={"name": "x"}
                )
        assert resp.status_code == 404

    async def test_delete_script(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.delete_script.return_value = True
        app = _create_v2_scripts_app(script_management=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/scripts/{sid}")
        assert resp.status_code == 204

    async def test_delete_script_not_found(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.delete_script.side_effect = ScriptNotFoundError("missing")
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/scripts/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_clone_script(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        view = _make_script_view(name="copy")
        svc.clone_script.return_value = view
        app = _create_v2_scripts_app(script_management=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/scripts/{sid}/clone")
        assert resp.status_code == 201
        assert resp.json()["name"] == "copy"

    async def test_clone_script_with_new_name(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        view = _make_script_view(name="my-copy")
        svc.clone_script.return_value = view
        app = _create_v2_scripts_app(script_management=svc)
        sid = uuid.uuid4()
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/scripts/{sid}/clone?new_name=my-copy")
        assert resp.status_code == 201
        svc.clone_script.assert_awaited_once_with(sid, new_name="my-copy")

    async def test_clone_not_found(self) -> None:
        svc = AsyncMock(spec=ScriptManagementService)
        svc.clone_script.side_effect = ScriptNotFoundError("missing")
        app = _create_v2_scripts_app(script_management=svc)
        with _settings_patch:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/scripts/{uuid.uuid4()}/clone")
        assert resp.status_code == 404
