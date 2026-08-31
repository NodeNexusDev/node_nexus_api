"""Unit tests for app/api/v2/commands.py — extra coverage.

Covers GET /?cursor, POST / bulk create 1..20 with 207, GET /history,
GET /stats with group_by, POST /executions M*N with command_ids and
node_ids/tags and params, raw-executions, GET /executions/history,
POST /executions/retries|cancels with 207, plus CRUD clone.
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
from app.api.v2.commands import router as commands_router
from app.application.dto.command_execution import (
    BulkCommandResultDTO,
    CommandExecutionDTO,
)
from app.application.dto.command_history import CommandHistoryDTO, CommandHistoryPageDTO
from app.application.dto.command_management import CommandParameterDTO, CommandViewDTO
from app.application.dto.execution_stats import ExecutionStatsDTO
from app.application.services.command_management_service import CommandManagementService
from app.application.services.execution_history_service import ExecutionHistoryService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.core.exceptions import CommandNotFoundError, DomainError
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode_offset(offset: int) -> str:
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _make_cmd_view(**overrides: object) -> CommandViewDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "check_disk",
        "description": "Check disk",
        "command": "df -h",
        "parameters": (),
        "tags": (),
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return CommandViewDTO(**defaults)  # type: ignore[arg-type]


def _make_param(
    name: str = "p",
    type_: str = "string",
    required: bool = True,
    default: object = None,
    description: str | None = None,
) -> CommandParameterDTO:
    return CommandParameterDTO(
        name=name,
        type=type_,  # ty: ignore[invalid-argument-type]
        required=required,
        default=default,  # ty: ignore[invalid-argument-type]
        description=description,
    )


def _make_history_dto(**overrides: object) -> CommandHistoryDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "command_id": None,
        "batch_id": uuid.uuid4(),
        "command_fingerprint": "abc",
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "stdout_bytes": 2,
        "stderr_bytes": 0,
        "truncated": False,
        "started_at": now,
        "finished_at": now,
        "created_at": now,
    }
    defaults.update(overrides)
    return CommandHistoryDTO(**defaults)  # type: ignore[arg-type]


def _make_stats_dto(**overrides: object) -> ExecutionStatsDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "total": 10,
        "successful": 8,
        "failed": 1,
        "cancelled": 1,
        "success_rate": 0.8,
        "avg_duration_ms": 100.0,
        "min_duration_ms": 10.0,
        "max_duration_ms": 200.0,
        "last_executed_at": now,
    }
    defaults.update(overrides)
    return ExecutionStatsDTO(**defaults)  # type: ignore[arg-type]


def _make_bulk_result(
    command: str = "echo hi",
    results: tuple[CommandExecutionDTO, ...] | None = None,
) -> BulkCommandResultDTO:
    if results is None:
        results = (
            CommandExecutionDTO(
                node_id=uuid.uuid4(),
                node_name="n1",
                stdout="ok",
                stderr="",
                exit_code=0,
            ),
        )
    succeeded = sum(1 for r in results if r.exit_code == 0)
    return BulkCommandResultDTO(
        command=command,
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


def _create_app(
    cmd_mgmt: AsyncMock | None = None,
    exec_history: AsyncMock | None = None,
    exec_stats: AsyncMock | None = None,
    bulk_cmd: AsyncMock | None = None,
    exec_lifecycle: AsyncMock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(commands_router, prefix="/api/v2")

    cm = cmd_mgmt or AsyncMock(spec=CommandManagementService)
    eh = exec_history or AsyncMock(spec=ExecutionHistoryService)
    es = exec_stats or AsyncMock(spec=ExecutionStatsService)
    bc = bulk_cmd or AsyncMock(spec=NodeBulkCommandService)
    el = exec_lifecycle or AsyncMock(spec=ExecutionLifecycleService)

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_cmd_mgmt(self) -> CommandManagementService:
            return as_typed_mock(CommandManagementService, cm)

        @provide(scope=Scope.REQUEST)
        def get_exec_history(self) -> ExecutionHistoryService:
            return as_typed_mock(ExecutionHistoryService, eh)

        @provide(scope=Scope.REQUEST)
        def get_exec_stats(self) -> ExecutionStatsService:
            return as_typed_mock(ExecutionStatsService, es)

        @provide(scope=Scope.REQUEST)
        def get_bulk_cmd(self) -> NodeBulkCommandService:
            return as_typed_mock(NodeBulkCommandService, bc)

        @provide(scope=Scope.REQUEST)
        def get_exec_lifecycle(self) -> ExecutionLifecycleService:
            return as_typed_mock(ExecutionLifecycleService, el)

    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


NODE_ID = uuid.uuid4()
NODE_ID2 = uuid.uuid4()
CMD_ID = uuid.uuid4()
CMD_ID2 = uuid.uuid4()
BATCH_ID = uuid.uuid4()
EXEC_ID = uuid.uuid4()
EXEC_ID2 = uuid.uuid4()

_settings_patcher = patch(
    "app.api.deps.get_settings", return_value=_mock_settings("test-master")
)


# ---------------------------------------------------------------------------
# GET /?cursor — list with cursor pagination
# ---------------------------------------------------------------------------


class TestListCommands:
    @pytest.mark.asyncio
    async def test_list_no_cursor(self) -> None:
        svc = AsyncMock()
        cmd = _make_cmd_view()
        svc.get_all_commands.return_value = ([cmd], 1)
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get("/api/v2/commands/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        svc.get_all_commands.assert_awaited_once_with(
            page=1, size=20, tags=None, search=None
        )

    @pytest.mark.asyncio
    async def test_list_with_tag_and_search(self) -> None:
        svc = AsyncMock()
        svc.get_all_commands.return_value = ([], 0)
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get("/api/v2/commands/?tag=ops&search=disk&limit=5")
        assert resp.status_code == 200
        svc.get_all_commands.assert_awaited_once_with(
            page=1, size=5, tags=["ops"], search="disk"
        )

    @pytest.mark.asyncio
    async def test_list_with_valid_cursor_has_more(self) -> None:
        svc = AsyncMock()
        c1 = _make_cmd_view(name="c1")
        # offset 0, limit 1, total 3 => has_more True => next_cursor offset 1
        svc.get_all_commands.return_value = ([c1], 3)
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get("/api/v2/commands/?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert data["next_cursor"] == _encode_offset(1)
        # follow cursor
        svc2 = AsyncMock()
        c2 = _make_cmd_view(name="c2")
        svc2.get_all_commands.return_value = ([c2], 3)
        app2 = _create_app(cmd_mgmt=svc2)
        cursor = _encode_offset(1)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app2),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp2 = await ac.get(f"/api/v2/commands/?cursor={cursor}&limit=1")
        assert resp2.status_code == 200
        # offset 1 //1 +1 =2
        svc2.get_all_commands.assert_awaited_once_with(
            page=2, size=1, tags=None, search=None
        )

    @pytest.mark.asyncio
    async def test_list_invalid_cursor(self) -> None:
        svc = AsyncMock()
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get("/api/v2/commands/?cursor=bad!!")
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"

    @pytest.mark.asyncio
    async def test_list_cursor_offset_translation(self) -> None:
        svc = AsyncMock()
        svc.get_all_commands.return_value = ([], 0)
        app = _create_app(cmd_mgmt=svc)
        cursor = _encode_offset(40)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(f"/api/v2/commands/?cursor={cursor}&limit=20")
        assert resp.status_code == 200
        svc.get_all_commands.assert_awaited_once_with(
            page=3, size=20, tags=None, search=None
        )


# ---------------------------------------------------------------------------
# POST / — bulk create 1..20 with 207
# ---------------------------------------------------------------------------


class TestBulkCreate:
    @pytest.mark.asyncio
    async def test_bulk_create_all_success(self) -> None:
        svc = AsyncMock()
        cmd = _make_cmd_view(name="new")
        svc.create_command.return_value = cmd
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/",
                    json={"items": [{"name": "new", "command": "echo hi"}]},
                )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0
        assert data["results"][0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_bulk_create_with_parameters_and_tags(self) -> None:
        svc = AsyncMock()
        cmd = _make_cmd_view(name="c1", tags=("ops",), parameters=(_make_param("x"),))
        svc.create_command.return_value = cmd
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/",
                    json={
                        "items": [
                            {
                                "name": "c1",
                                "command": "echo {x}",
                                "parameters": [
                                    {"name": "x", "type": "string", "required": True}
                                ],
                                "tags": ["ops"],
                            }
                        ]
                    },
                )
        assert resp.status_code == 201
        assert resp.json()["succeeded"] == 1

    @pytest.mark.asyncio
    async def test_bulk_create_partial_207(self) -> None:
        svc = AsyncMock()

        def _side(dto):  # type: ignore[no-untyped-def]
            if dto.name == "good":
                return _make_cmd_view(name="good")
            raise ValueError("dup name")

        svc.create_command.side_effect = _side
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/",
                    json={
                        "items": [
                            {"name": "good", "command": "echo hi"},
                            {"name": "bad", "command": "echo hi"},
                        ]
                    },
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        statuses = {r["status"] for r in data["results"]}
        assert statuses == {"success", "error"}

    @pytest.mark.asyncio
    async def test_bulk_create_all_error_stays_201(self) -> None:
        svc = AsyncMock()
        svc.create_command.side_effect = ValueError("fail")
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/",
                    json={
                        "items": [
                            {"name": "a", "command": "echo hi"},
                            {"name": "b", "command": "echo hi"},
                        ]
                    },
                )
        assert resp.status_code == 201
        data = resp.json()
        assert data["succeeded"] == 0
        assert data["failed"] == 2

    @pytest.mark.asyncio
    async def test_bulk_create_validation_empty(self) -> None:
        svc = AsyncMock()
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post("/api/v2/commands/", json={"items": []})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_create_too_many(self) -> None:
        svc = AsyncMock()
        app = _create_app(cmd_mgmt=svc)
        items = [{"name": f"c{i}", "command": "echo hi"} for i in range(21)]
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post("/api/v2/commands/", json={"items": items})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_history_no_cursor(self) -> None:
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_node_history.return_value = CommandHistoryPageDTO(items=(dto,), total=1)
        app = _create_app(exec_history=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(f"/api/v2/commands/history?node_id={NODE_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["has_more"] is False
        svc.get_node_history.assert_awaited_once_with(NODE_ID, page=1, size=20)

    @pytest.mark.asyncio
    async def test_history_with_cursor_and_limit(self) -> None:
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_node_history.return_value = CommandHistoryPageDTO(items=(dto,), total=5)
        app = _create_app(exec_history=svc)
        cursor = _encode_offset(0)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/history?node_id={NODE_ID}&cursor={cursor}&limit=20"
                )
        assert resp.status_code == 200
        assert resp.json()["has_more"] is True
        assert resp.json()["next_cursor"] == _encode_offset(20)
        svc.get_node_history.assert_awaited_once_with(NODE_ID, page=1, size=20)

    @pytest.mark.asyncio
    async def test_history_invalid_cursor(self) -> None:
        svc = AsyncMock()
        app = _create_app(exec_history=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/history?node_id={NODE_ID}&cursor=bad"
                )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_history_has_more_false_when_last_page(self) -> None:
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_node_history.return_value = CommandHistoryPageDTO(items=(dto,), total=1)
        app = _create_app(exec_history=svc)
        cursor = _encode_offset(0)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/history?node_id={NODE_ID}&cursor={cursor}&limit=20"
                )
        assert resp.json()["has_more"] is False
        assert resp.json()["next_cursor"] is None


# ---------------------------------------------------------------------------
# GET /stats with group_by
# ---------------------------------------------------------------------------


class TestGetStats:
    @pytest.mark.asyncio
    async def test_stats_no_group_by_no_node(self) -> None:
        svc = AsyncMock()
        svc.get_command_stats.return_value = _make_stats_dto()
        app = _create_app(exec_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get("/api/v2/commands/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        svc.get_command_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stats_no_group_by_with_node(self) -> None:
        svc = AsyncMock()
        svc.get_node_command_stats.return_value = _make_stats_dto(
            total=5, successful=5, failed=0
        )
        app = _create_app(exec_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(f"/api/v2/commands/stats?node_id={NODE_ID}")
        assert resp.status_code == 200
        assert resp.json()["total"] == 5
        svc.get_node_command_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stats_with_group_by_no_node(self) -> None:
        svc = AsyncMock()
        svc.get_command_stats.return_value = _make_stats_dto()
        app = _create_app(exec_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get("/api/v2/commands/stats?group_by=day")
        assert resp.status_code == 200
        data = resp.json()
        assert "buckets" in data
        assert len(data["buckets"]) == 1
        assert data["buckets"][0]["period"] == "all"

    @pytest.mark.asyncio
    async def test_stats_with_group_by_and_node_and_dates(self) -> None:
        svc = AsyncMock()
        svc.get_node_command_stats.return_value = _make_stats_dto(total=2)
        app = _create_app(exec_stats=svc)
        date_from = "2024-01-01T00:00:00Z"
        date_to = "2024-01-31T00:00:00Z"
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/stats?node_id={NODE_ID}&group_by=hour&date_from={date_from}&date_to={date_to}"
                )
        assert resp.status_code == 200
        data = resp.json()
        assert (
            data["buckets"][0]["period"] == date_from
            or "2024-01-01" in data["buckets"][0]["period"]
        )

    @pytest.mark.asyncio
    async def test_stats_with_group_by_date_from_period(self) -> None:
        svc = AsyncMock()
        svc.get_command_stats.return_value = _make_stats_dto()
        app = _create_app(exec_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    "/api/v2/commands/stats?group_by=week&date_from=2024-01-01T00:00:00Z"
                )
        assert resp.status_code == 200
        assert resp.json()["buckets"][0]["period"] == "2024-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# POST /executions M*N
# ---------------------------------------------------------------------------


class TestBulkExecutions:
    @pytest.mark.asyncio
    async def test_executions_success_single(self) -> None:
        cmd_svc = AsyncMock()
        cmd_svc.get_command.return_value = _make_cmd_view(
            id=CMD_ID, command="echo hi", parameters=()
        )
        bulk = AsyncMock()
        exec_res = CommandExecutionDTO(
            node_id=NODE_ID, node_name="n1", stdout="hi", stderr="", exit_code=0
        )
        bulk.execute.return_value = _make_bulk_result(results=(exec_res,))
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={"command_ids": [str(CMD_ID)], "node_ids": [str(NODE_ID)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0
        assert "batch_id" in data

    @pytest.mark.asyncio
    async def test_executions_with_tags_and_params(self) -> None:
        cmd_svc = AsyncMock()
        param = _make_param("name", required=True)
        cmd_svc.get_command.return_value = _make_cmd_view(
            id=CMD_ID, command="echo {name}", parameters=(param,)
        )
        bulk = AsyncMock()
        exec_res = CommandExecutionDTO(
            node_id=NODE_ID, node_name="n1", stdout="hello", stderr="", exit_code=0
        )
        bulk.execute.return_value = _make_bulk_result(
            results=(exec_res,), command="echo 'world'"
        )
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={
                        "command_ids": [str(CMD_ID)],
                        "node_tags": ["ops"],
                        "params": {str(CMD_ID): {"name": "world"}},
                    },
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 1
        # verify rendered command passed to bulk
        args = bulk.execute.await_args.args[0]
        assert "world" in args.command

    @pytest.mark.asyncio
    async def test_executions_207_partial(self) -> None:
        cmd_svc = AsyncMock()
        cmd_svc.get_command.return_value = _make_cmd_view(id=CMD_ID, command="echo hi")
        bulk = AsyncMock()
        ok = CommandExecutionDTO(
            node_id=NODE_ID, node_name="n1", stdout="ok", stderr="", exit_code=0
        )
        fail = CommandExecutionDTO(
            node_id=NODE_ID2, node_name="n2", stdout="", stderr="err", exit_code=1
        )
        bulk.execute.return_value = _make_bulk_result(results=(ok, fail))
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={
                        "command_ids": [str(CMD_ID)],
                        "node_ids": [str(NODE_ID), str(NODE_ID2)],
                    },
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    @pytest.mark.asyncio
    async def test_executions_mn_guard(self) -> None:
        cmd_svc = AsyncMock()
        bulk = AsyncMock()
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        cmd_ids = [str(uuid.uuid4()) for _ in range(20)]
        node_ids = [str(uuid.uuid4()) for _ in range(6)]  # 20*6=120 >100
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={"command_ids": cmd_ids, "node_ids": node_ids},
                )
        assert resp.status_code == 422
        assert "M×N" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_executions_mn_guard_with_tags(self) -> None:
        cmd_svc = AsyncMock()
        bulk = AsyncMock()
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        cmd_ids = [str(uuid.uuid4()) for _ in range(11)]
        tags = [f"t{i}" for i in range(10)]  # 11*10=110 >100
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={"command_ids": cmd_ids, "node_tags": tags},
                )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_executions_render_error(self) -> None:
        cmd_svc = AsyncMock()
        # command expects param but not provided
        param = _make_param("name", required=True)
        cmd_svc.get_command.return_value = _make_cmd_view(
            id=CMD_ID, command="echo {name}", parameters=(param,)
        )
        bulk = AsyncMock()
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={
                        "command_ids": [str(CMD_ID)],
                        "node_ids": [str(NODE_ID)],
                        "params": {},
                    },
                )
        # render raises TemplateRenderError -> handled as error item
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_executions_get_command_not_found(self) -> None:
        cmd_svc = AsyncMock()
        cmd_svc.get_command.side_effect = CommandNotFoundError("not found")
        bulk = AsyncMock()
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={"command_ids": [str(CMD_ID)], "node_ids": [str(NODE_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1
        assert resp.json()["results"][0]["stderr"] != ""

    @pytest.mark.asyncio
    async def test_executions_bulk_service_exception(self) -> None:
        cmd_svc = AsyncMock()
        cmd_svc.get_command.return_value = _make_cmd_view(id=CMD_ID, command="echo hi")
        bulk = AsyncMock()
        bulk.execute.side_effect = RuntimeError("ssh fail")
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={"command_ids": [str(CMD_ID)], "node_ids": [str(NODE_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1

    @pytest.mark.asyncio
    async def test_executions_multiple_commands(self) -> None:
        cmd_svc = AsyncMock()

        def _get(cid):  # type: ignore[no-untyped-def]
            return _make_cmd_view(id=cid, command=f"echo {cid}")

        cmd_svc.get_command.side_effect = _get
        bulk = AsyncMock()
        bulk.execute.return_value = _make_bulk_result(
            results=(
                CommandExecutionDTO(
                    node_id=NODE_ID, node_name="n1", stdout="ok", stderr="", exit_code=0
                ),
            )
        )
        app = _create_app(cmd_mgmt=cmd_svc, bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions",
                    json={
                        "command_ids": [str(CMD_ID), str(CMD_ID2)],
                        "node_ids": [str(NODE_ID)],
                    },
                )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2


# ---------------------------------------------------------------------------
# POST /raw-executions
# ---------------------------------------------------------------------------


class TestRawExecutions:
    @pytest.mark.asyncio
    async def test_raw_success(self) -> None:
        bulk = AsyncMock()
        exec_res = CommandExecutionDTO(
            node_id=NODE_ID, node_name="n1", stdout="ok", stderr="", exit_code=0
        )
        bulk.execute.return_value = _make_bulk_result(
            results=(exec_res,), command="echo hi"
        )
        app = _create_app(bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/raw-executions",
                    json={"commands": ["echo hi"], "node_ids": [str(NODE_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    @pytest.mark.asyncio
    async def test_raw_with_tags(self) -> None:
        bulk = AsyncMock()
        exec_res = CommandExecutionDTO(
            node_id=NODE_ID, node_name="n1", stdout="ok", stderr="", exit_code=0
        )
        bulk.execute.return_value = _make_bulk_result(results=(exec_res,))
        app = _create_app(bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/raw-executions",
                    json={"commands": ["echo hi"], "node_tags": ["ops"]},
                )
        assert resp.status_code == 200
        args = bulk.execute.await_args.args[0]
        assert args.tags == ("ops",)

    @pytest.mark.asyncio
    async def test_raw_207(self) -> None:
        bulk = AsyncMock()
        ok = CommandExecutionDTO(
            node_id=NODE_ID, node_name="n1", stdout="ok", stderr="", exit_code=0
        )
        fail = CommandExecutionDTO(
            node_id=NODE_ID2, node_name="n2", stdout="", stderr="err", exit_code=1
        )
        bulk.execute.return_value = _make_bulk_result(results=(ok, fail))
        app = _create_app(bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/raw-executions",
                    json={
                        "commands": ["echo hi"],
                        "node_ids": [str(NODE_ID), str(NODE_ID2)],
                    },
                )
        # bulk returns 1 cmd *2 nodes but mixed per bulk result
        assert resp.status_code == 207

    @pytest.mark.asyncio
    async def test_raw_guard(self) -> None:
        bulk = AsyncMock()
        app = _create_app(bulk_cmd=bulk)
        cmds = [f"echo {i}" for i in range(20)]
        node_ids = [str(uuid.uuid4()) for _ in range(6)]
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/raw-executions",
                    json={"commands": cmds, "node_ids": node_ids},
                )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_raw_bulk_exception(self) -> None:
        bulk = AsyncMock()
        bulk.execute.side_effect = RuntimeError("fail")
        app = _create_app(bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/raw-executions",
                    json={"commands": ["echo hi"], "node_ids": [str(NODE_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1

    @pytest.mark.asyncio
    async def test_raw_multiple_commands(self) -> None:
        bulk = AsyncMock()
        bulk.execute.return_value = _make_bulk_result(
            results=(
                CommandExecutionDTO(
                    node_id=NODE_ID, node_name="n1", stdout="ok", stderr="", exit_code=0
                ),
            )
        )
        app = _create_app(bulk_cmd=bulk)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/raw-executions",
                    json={"commands": ["echo a", "echo b"], "node_ids": [str(NODE_ID)]},
                )
        assert resp.json()["total"] == 2


# ---------------------------------------------------------------------------
# GET /executions/history
# ---------------------------------------------------------------------------


class TestExecutionsHistory:
    @pytest.mark.asyncio
    async def test_exec_history_no_cursor(self) -> None:
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_batch_history.return_value = CommandHistoryPageDTO(
            items=(dto,), total=1
        )
        app = _create_app(exec_history=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/executions/history?batch_id={BATCH_ID}"
                )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        svc.get_batch_history.assert_awaited_once_with(BATCH_ID, page=1, size=20)

    @pytest.mark.asyncio
    async def test_exec_history_with_cursor(self) -> None:
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_batch_history.return_value = CommandHistoryPageDTO(
            items=(dto,), total=5
        )
        app = _create_app(exec_history=svc)
        cursor = _encode_offset(0)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/executions/history?batch_id={BATCH_ID}&cursor={cursor}&limit=20"
                )
        assert resp.status_code == 200
        assert resp.json()["has_more"] is True
        svc.get_batch_history.assert_awaited_once_with(BATCH_ID, page=1, size=20)

    @pytest.mark.asyncio
    async def test_exec_history_invalid_cursor(self) -> None:
        svc = AsyncMock()
        app = _create_app(exec_history=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/executions/history?batch_id={BATCH_ID}&cursor=bad"
                )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_exec_history_missing_batch_id(self) -> None:
        svc = AsyncMock()
        app = _create_app(exec_history=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get("/api/v2/commands/executions/history")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /executions/retries|cancels with 207
# ---------------------------------------------------------------------------


class TestBulkRetriesCancels:
    @pytest.mark.asyncio
    async def test_retry_all_success(self) -> None:
        svc = AsyncMock()
        svc.retry_command.return_value = MagicMock()
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/retries",
                    json={"execution_ids": [str(EXEC_ID)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 0

    @pytest.mark.asyncio
    async def test_retry_partial_207(self) -> None:
        svc = AsyncMock()

        async def _retry(dto):  # type: ignore[no-untyped-def]
            if str(dto.execution_id) == str(EXEC_ID):
                return MagicMock()
            raise RuntimeError("not found")

        svc.retry_command.side_effect = _retry
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/retries",
                    json={"execution_ids": [str(EXEC_ID), str(EXEC_ID2)]},
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    @pytest.mark.asyncio
    async def test_retry_all_error(self) -> None:
        svc = AsyncMock()
        svc.retry_command.side_effect = RuntimeError("fail")
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/retries",
                    json={"execution_ids": [str(EXEC_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1

    @pytest.mark.asyncio
    async def test_cancel_all_success(self) -> None:
        svc = AsyncMock()
        svc.cancel_execution.return_value = True
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/cancels",
                    json={"execution_ids": [str(EXEC_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    @pytest.mark.asyncio
    async def test_cancel_partial_207(self) -> None:
        svc = AsyncMock()

        async def _cancel(dto):  # type: ignore[no-untyped-def]
            if str(dto.execution_id) == str(EXEC_ID):
                return True
            raise RuntimeError("not found")

        svc.cancel_execution.side_effect = _cancel
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/cancels",
                    json={"execution_ids": [str(EXEC_ID), str(EXEC_ID2)]},
                )
        assert resp.status_code == 207
        assert resp.json()["succeeded"] == 1
        assert resp.json()["failed"] == 1

    @pytest.mark.asyncio
    async def test_cancel_all_error(self) -> None:
        svc = AsyncMock()
        svc.cancel_execution.side_effect = RuntimeError("fail")
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/cancels",
                    json={"execution_ids": [str(EXEC_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1

    @pytest.mark.asyncio
    async def test_retry_empty_validation(self) -> None:
        svc = AsyncMock()
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/retries", json={"execution_ids": []}
                )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_cancel_empty_validation(self) -> None:
        svc = AsyncMock()
        app = _create_app(exec_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    "/api/v2/commands/executions/cancels", json={"execution_ids": []}
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# CRUD + clone + per-command stats
# ---------------------------------------------------------------------------


class TestCrudClone:
    @pytest.mark.asyncio
    async def test_get_command_found(self) -> None:
        svc = AsyncMock()
        cmd = _make_cmd_view(id=CMD_ID)
        svc.get_command.return_value = cmd
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(f"/api/v2/commands/{CMD_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(CMD_ID)

    @pytest.mark.asyncio
    async def test_get_command_not_found(self) -> None:
        svc = AsyncMock()
        svc.get_command.side_effect = CommandNotFoundError("not found")
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(f"/api/v2/commands/{CMD_ID}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_command(self) -> None:
        svc = AsyncMock()
        updated = _make_cmd_view(id=CMD_ID, name="updated")
        svc.update_command.return_value = updated
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/commands/{CMD_ID}", json={"name": "updated"}
                )
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated"

    @pytest.mark.asyncio
    async def test_update_with_parameters_and_tags(self) -> None:
        svc = AsyncMock()
        updated = _make_cmd_view(id=CMD_ID, tags=("a",))
        svc.update_command.return_value = updated
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/commands/{CMD_ID}",
                    json={
                        "tags": ["a"],
                        "parameters": [{"name": "x", "type": "integer"}],
                    },
                )
        assert resp.status_code == 200
        # check service called with converted DTO
        call = svc.update_command.await_args
        assert call is not None
        dto = call.args[1]
        changes = dict(dto.changes)
        assert isinstance(changes.get("tags"), tuple)
        assert isinstance(changes.get("parameters"), tuple)

    @pytest.mark.asyncio
    async def test_update_not_found(self) -> None:
        svc = AsyncMock()
        svc.update_command.side_effect = CommandNotFoundError("not found")
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.patch(f"/api/v2/commands/{CMD_ID}", json={"name": "x"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        svc = AsyncMock()
        svc.delete_command.return_value = True
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.delete(f"/api/v2/commands/{CMD_ID}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_not_found(self) -> None:
        svc = AsyncMock()
        svc.delete_command.side_effect = CommandNotFoundError("not found")
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.delete(f"/api/v2/commands/{CMD_ID}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_clone_success(self) -> None:
        svc = AsyncMock()
        cloned = _make_cmd_view(name="check_disk-copy")
        svc.clone_command.return_value = cloned
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(f"/api/v2/commands/{CMD_ID}/clone")
        assert resp.status_code == 201
        assert "copy" in resp.json()["name"]

    @pytest.mark.asyncio
    async def test_clone_with_new_name(self) -> None:
        svc = AsyncMock()
        cloned = _make_cmd_view(name="my-clone")
        svc.clone_command.return_value = cloned
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/commands/{CMD_ID}/clone?new_name=my-clone"
                )
        assert resp.status_code == 201
        svc.clone_command.assert_awaited_once_with(CMD_ID, new_name="my-clone")

    @pytest.mark.asyncio
    async def test_clone_not_found(self) -> None:
        svc = AsyncMock()
        svc.clone_command.side_effect = CommandNotFoundError("not found")
        app = _create_app(cmd_mgmt=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.post(f"/api/v2/commands/{CMD_ID}/clone")
        assert resp.status_code == 404


class TestPerCommandStats:
    @pytest.mark.asyncio
    async def test_per_command_stats_no_group_by(self) -> None:
        svc = AsyncMock()
        svc.get_command_stats.return_value = _make_stats_dto()
        app = _create_app(exec_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(f"/api/v2/commands/{CMD_ID}/stats")
        assert resp.status_code == 200
        assert resp.json()["total"] == 10
        svc.get_command_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_per_command_stats_with_group_by(self) -> None:
        svc = AsyncMock()
        svc.get_command_stats.return_value = _make_stats_dto()
        app = _create_app(exec_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(f"/api/v2/commands/{CMD_ID}/stats?group_by=day")
        assert resp.status_code == 200
        assert "buckets" in resp.json()

    @pytest.mark.asyncio
    async def test_per_command_stats_with_dates(self) -> None:
        svc = AsyncMock()
        svc.get_command_stats.return_value = _make_stats_dto()
        app = _create_app(exec_stats=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
                follow_redirects=True,
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/commands/{CMD_ID}/stats?group_by=hour&date_from=2024-01-01T00:00:00Z"
                )
        assert resp.status_code == 200
        assert resp.json()["buckets"][0]["period"] == "2024-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers direct
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_encode_decode_offset(self) -> None:
        from app.api.v2.commands import _decode_offset, _encode_offset

        for off in [0, 1, 20, 100]:
            cur = _encode_offset(off)
            assert _decode_offset(cur) == off

    def test_decode_invalid(self) -> None:
        from app.api.v2.commands import _decode_offset

        try:
            _decode_offset("bad!!")
            raise AssertionError("should raise")
        except ValueError as exc:
            assert "Invalid cursor" in str(exc)

    def test_parameter_dto_and_response(self) -> None:
        from app.api.v2.commands import _command_response, _parameter_dto
        from app.schemas.command import CommandParameter

        param = CommandParameter(name="x", type="string", required=True)
        dto = _parameter_dto(param)
        assert dto.name == "x"
        view = _make_cmd_view(parameters=(dto,), tags=("a",))
        resp = _command_response(view)
        assert resp.name == view.name
        assert resp.tags == ["a"]

    def test_decode_offset_invalid_json(self) -> None:
        from app.api.v2.commands import _decode_offset

        cur = base64.urlsafe_b64encode(b"not json").decode()
        try:
            _decode_offset(cur)
            raise AssertionError
        except ValueError:
            pass
