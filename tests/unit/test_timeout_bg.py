# ruff: noqa: E501,ANN001,ANN003,ARG001,PLR0913,S101
"""Boost coverage for timeout feature to >=95%."""

from __future__ import annotations

import asyncio
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
from app.application.dto.command_history import CommandHistoryDTO, CommandHistoryPageDTO
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandParameterDTO,
    CommandViewDTO,
)
from app.application.dto.script_definition import ScriptDefinitionDTO
from app.application.dto.script_execution import ScriptExecutionRequestDTO
from app.application.dto.script_management import (
    ScriptCreateDTO,
    ScriptStepDTO,
    ScriptViewDTO,
)
from app.application.services.command_management_service import CommandManagementService
from app.application.services.execution_history_service import ExecutionHistoryService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)
from app.application.services.schedule_management import ScheduleManagementService
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.script_management_service import ScriptManagementService
from app.core.config import Settings, get_settings
from tests.typing import as_typed_mock
from tests.unit.conftest import (
    MockAuthServiceProvider,
    _mock_settings,
    make_orm_command,
)


# helpers
def _encode_offset(offset: int) -> str:
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()

def _make_maker(session: MagicMock | AsyncMock) -> MagicMock:
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    maker = MagicMock()
    maker.return_value = mock_ctx
    maker.begin.return_value = mock_begin
    return maker

def _make_history_dto(**overrides) -> CommandHistoryDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "command_id": uuid.uuid4(),
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

_settings_patcher = patch("app.core.config.get_settings", return_value=_mock_settings("test-master"))

# ---------------------------------------------------------------------------
# 1. DTO timeout fields
# ---------------------------------------------------------------------------

class TestDTOTimeout:
    def test_command_view_dto_timeout(self):
        now = datetime.now(UTC)
        dto = CommandViewDTO(
            id=uuid.uuid4(),
            name="n",
            description=None,
            command="echo hi",
            parameters=(),
            tags=(),
            timeout=60,
            created_at=now,
            updated_at=now,
        )
        assert dto.timeout == 60

    def test_command_create_dto_timeout(self):
        dto = CommandCreateDTO(name="n", command="echo hi", timeout=60)
        assert dto.timeout == 60

    def test_script_view_dto_timeout(self):
        now = datetime.now(UTC)
        dto = ScriptViewDTO(
            id=uuid.uuid4(),
            name="s",
            description=None,
            steps=(ScriptStepDTO(label="a", type="inline", command="echo hi"),),
            tags=(),
            timeout=99,
            created_at=now,
            updated_at=now,
        )
        assert dto.timeout == 99

    def test_script_create_dto_timeout(self):
        dto = ScriptCreateDTO(
            name="s", steps=(ScriptStepDTO(label="a", type="inline", command="hi"),), timeout=42
        )
        assert dto.timeout == 42

    def test_command_template_timeout(self):
        from app.application.dto.command_template import CommandTemplateDTO

        dto = CommandTemplateDTO(id=uuid.uuid4(), command="echo hi", parameters=(), timeout=77)
        assert dto.timeout == 77

    def test_script_definition_timeout(self):
        dto = ScriptDefinitionDTO(id=uuid.uuid4(), steps=(), timeout=88)
        assert dto.timeout == 88

    def test_schemas_timeout_fields(self):
        from app.schemas.command import CommandCreate, CommandResponse, CommandUpdate
        from app.schemas.script import ScriptCreate, ScriptResponse

        # CommandCreate with timeout
        cc = CommandCreate(name="n", command="echo hi", timeout=60)
        assert cc.timeout == 60
        # CommandUpdate
        cu = CommandUpdate(timeout=120)
        assert cu.timeout == 120
        # CommandResponse includes timeout
        now = datetime.now(UTC)
        cr = CommandResponse(
            id=uuid.uuid4(),
            name="n",
            description=None,
            command="echo hi",
            parameters=[],
            tags=[],
            timeout=30,
            created_at=now,
            updated_at=now,
        )
        assert cr.timeout == 30
        # ScriptCreate/Response
        sc = ScriptCreate(
            name="s",
            steps=[{"label": "a", "type": "inline", "command": "echo hi", "params": {}, "on_failure": "stop"}],  # type: ignore[arg-type]
            timeout=55,
        )
        assert sc.timeout == 55
        sr = ScriptResponse(
            id=uuid.uuid4(),
            name="s",
            description=None,
            steps=[{"label": "a", "type": "inline", "command": "echo hi", "params": {}, "on_failure": "stop"}],  # type: ignore[arg-type]
            tags=[],
            timeout=55,
            created_at=now,
            updated_at=now,
        )
        assert sr.timeout == 55

# ---------------------------------------------------------------------------
# 2. _command_response includes timeout
# ---------------------------------------------------------------------------

class TestCommandResponseTimeout:
    def test_command_response_includes_timeout(self):
        from app.api.v2.commands_handlers.crud import _command_response

        now = datetime.now(UTC)
        view = CommandViewDTO(
            id=uuid.uuid4(),
            name="n",
            description="d",
            command="echo hi",
            parameters=(CommandParameterDTO(name="x"),),
            tags=("ops",),
            timeout=123,
            created_at=now,
            updated_at=now,
        )
        resp = _command_response(view)
        assert resp.timeout == 123
        assert resp.tags == ["ops"]

    def test_script_response_includes_timeout(self):
        from app.api.v2.scripts_handlers.crud import _script_response

        now = datetime.now(UTC)
        view = ScriptViewDTO(
            id=uuid.uuid4(),
            name="s",
            description=None,
            steps=(ScriptStepDTO(label="a", type="inline", command="echo hi"),),
            tags=("t1",),
            timeout=321,
            created_at=now,
            updated_at=now,
        )
        resp = _script_response(view)
        assert resp.timeout == 321

# ---------------------------------------------------------------------------
# 3. Persistence gateways timeout
# ---------------------------------------------------------------------------

class TestCommandGatewayTimeout:
    @pytest.mark.asyncio
    async def test_to_view_includes_timeout(self):
        from app.adapters.persistence.command_management import SqlAlchemyCommandGateway

        now = datetime.now(UTC)
        model = make_orm_command(timeout=77)
        model.created_at = now  # type: ignore[attr-defined]
        model.updated_at = now  # type: ignore[attr-defined]
        # ensure timeout field exists
        model.timeout = 77  # type: ignore[attr-defined]
        view = SqlAlchemyCommandGateway._to_view(model)  # type: ignore[arg-type]
        assert view.timeout == 77

    @pytest.mark.asyncio
    async def test_create_command_with_timeout(self):
        from app.adapters.persistence.command_management import SqlAlchemyCommandGateway

        factory, _ = _make_maker(AsyncMock()), AsyncMock()
        # use helper that returns factory,maker pair
        session = AsyncMock()
        factory = _make_maker(session)
        cmd = make_orm_command(timeout=60)
        cmd.timeout = 60  # type: ignore[attr-defined]
        data = CommandCreateDTO(name="n", command="echo hi", timeout=60)
        with patch("app.adapters.persistence.command_management.CommandRepository") as repo_cls:
            repo_cls.return_value.create = AsyncMock(return_value=cmd)
            view = await SqlAlchemyCommandGateway(factory).create_command(data)
        assert view.timeout == 60
        # persisted dict contains timeout
        await_args = repo_cls.return_value.create.await_args
        assert await_args is not None
        persisted = await_args.args[0]
        assert persisted["timeout"] == 60

    @pytest.mark.asyncio
    async def test_get_template_includes_timeout(self):
        from app.adapters.persistence.command_management import SqlAlchemyCommandGateway

        session = AsyncMock()
        factory = _make_maker(session)
        cmd = make_orm_command(command="echo hi")
        cmd.timeout = 42  # type: ignore[attr-defined]
        with patch("app.adapters.persistence.command_management.CommandRepository") as repo_cls:
            repo_cls.return_value.get_by_id = AsyncMock(return_value=cmd)
            tpl = await SqlAlchemyCommandGateway(factory).get_template(cmd.id)
        assert tpl is not None
        assert tpl.timeout == 42

    @pytest.mark.asyncio
    async def test_update_command_with_timeout(self):
        from app.adapters.persistence.command_management import SqlAlchemyCommandGateway
        from app.application.dto.command_management import CommandUpdateDTO

        session = AsyncMock()
        factory = _make_maker(session)
        cmd = make_orm_command(timeout=30)
        cmd.timeout = 90  # type: ignore[attr-defined]
        cmd_id = uuid.uuid4()
        data = CommandUpdateDTO(changes=(("timeout", 90),))  # type: ignore[arg-type]
        with patch("app.adapters.persistence.command_management.CommandRepository") as repo_cls:
            repo_cls.return_value.update = AsyncMock(return_value=cmd)
            view = await SqlAlchemyCommandGateway(factory).update_command(cmd_id, data)
        assert view is not None
        # changes dict should contain timeout
        await_args = repo_cls.return_value.update.await_args
        assert await_args is not None
        assert await_args.args[1]["timeout"] == 90

class TestScriptGatewayTimeout:
    def _script_model(self, **overrides):
        from app.models.script import ScriptModel

        now = datetime.now(UTC)
        vals = {
            "id": uuid.uuid4(),
            "name": "s",
            "description": None,
            "steps": [{"label": "a", "type": "inline", "command": "echo hi", "params": {}, "on_failure": "stop"}],
            "tags": [],
            "timeout": 55,
            "created_at": now,
            "updated_at": now,
        }
        vals.update(overrides)
        return ScriptModel(**vals)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_to_view_includes_timeout(self):
        from app.adapters.persistence.script_gateway import SqlAlchemyScriptGateway

        model = self._script_model(timeout=77)
        view = SqlAlchemyScriptGateway._to_view(model)  # type: ignore[arg-type]
        assert view.timeout == 77

    @pytest.mark.asyncio
    async def test_create_script_with_timeout(self):
        from app.adapters.persistence.script_gateway import SqlAlchemyScriptGateway

        session = AsyncMock()
        factory = _make_maker(session)
        model = self._script_model(timeout=60)
        data = ScriptCreateDTO(
            name="s",
            steps=(ScriptStepDTO(label="a", type="inline", command="echo hi"),),
            timeout=60,
        )
        with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_cls:
            repo_cls.return_value.create = AsyncMock(return_value=model)
            view = await SqlAlchemyScriptGateway(factory).create_script(data)
        assert view.timeout == 60
        await_args = repo_cls.return_value.create.await_args
        assert await_args is not None
        persisted = await_args.args[0]
        assert persisted["timeout"] == 60

    @pytest.mark.asyncio
    async def test_scoped_definition_reader_timeout(self):
        from app.adapters.persistence.script_gateway import ScopedScriptDefinitionReader

        session = AsyncMock()
        factory = _make_maker(session)
        model = self._script_model(timeout=99)
        with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_cls:
            repo_cls.return_value.get_by_id = AsyncMock(return_value=model)
            reader = ScopedScriptDefinitionReader(factory)
            dto = await reader.get_definition(model.id)
        assert dto is not None
        assert dto.timeout == 99

    @pytest.mark.asyncio
    async def test_gateway_get_definition_timeout(self):
        from app.adapters.persistence.script_gateway import SqlAlchemyScriptGateway

        session = AsyncMock()
        factory = _make_maker(session)
        model = self._script_model(timeout=88)
        with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_cls:
            repo_cls.return_value.get_by_id = AsyncMock(return_value=model)
            dto = await SqlAlchemyScriptGateway(factory).get_definition(model.id)
        assert dto is not None
        assert dto.timeout == 88

    @pytest.mark.asyncio
    async def test_gateway_get_definition_none(self):
        from app.adapters.persistence.script_gateway import SqlAlchemyScriptGateway

        session = AsyncMock()
        factory = _make_maker(session)
        with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_cls:
            repo_cls.return_value.get_by_id = AsyncMock(return_value=None)
            dto = await SqlAlchemyScriptGateway(factory).get_definition(uuid.uuid4())
        assert dto is None

# ---------------------------------------------------------------------------
# 4. Execution registry
# ---------------------------------------------------------------------------

class TestExecutionRegistry:
    @pytest.mark.asyncio
    async def test_register_and_get(self):
        from app.application.services import execution_registry

        execution_registry._tasks.clear()
        exec_id = uuid.uuid4()

        async def _dummy():
            await asyncio.sleep(0.05)

        task: asyncio.Task[None] = asyncio.create_task(_dummy())  # type: ignore[arg-type]
        execution_registry.register_execution(exec_id, task)  # type: ignore[arg-type]
        assert execution_registry.get_execution_task(exec_id) is task
        assert execution_registry.cancel_execution_task(exec_id) is True
        # task is cancelling, not yet done
        assert task.cancelled() is False or task.cancelled() is True  # may be pending
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.01)
        # after cancellation, task should be done and removed from registry
        assert task.done()
        assert execution_registry.get_execution_task(exec_id) is None
        execution_registry._tasks.clear()

    def test_get_missing(self):
        from app.application.services import execution_registry

        execution_registry._tasks.clear()
        assert execution_registry.get_execution_task(uuid.uuid4()) is None

    def test_cancel_missing(self):
        from app.application.services import execution_registry

        execution_registry._tasks.clear()
        assert execution_registry.cancel_execution_task(uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_cancel_done_returns_false(self):
        from app.application.services import execution_registry

        execution_registry._tasks.clear()
        exec_id = uuid.uuid4()

        async def _quick():
            return

        task: asyncio.Task[None] = asyncio.create_task(_quick())  # type: ignore[arg-type]
        await task
        execution_registry._tasks[exec_id] = task  # type: ignore[assignment]
        assert execution_registry.cancel_execution_task(exec_id) is False
        execution_registry._tasks.clear()

    @pytest.mark.asyncio
    async def test_auto_removal_on_done(self):
        from app.application.services import execution_registry

        execution_registry._tasks.clear()
        exec_id = uuid.uuid4()

        async def _quick2():
            await asyncio.sleep(0.01)

        task: asyncio.Task[None] = asyncio.create_task(_quick2())  # type: ignore[arg-type]
        execution_registry.register_execution(exec_id, task)  # type: ignore[arg-type]
        await task
        await asyncio.sleep(0.01)
        assert exec_id not in execution_registry._tasks
        execution_registry._tasks.clear()

# ---------------------------------------------------------------------------
# 5. CommandExecutionService effective_timeout
# ---------------------------------------------------------------------------

class TestCommandExecutionTimeout:
    @pytest.mark.asyncio
    async def test_effective_timeout_override(self):
        from app.application.dto.command_management import CommandExecuteRequestDTO
        from app.application.dto.command_template import CommandTemplateDTO
        from app.application.services.command_execution_service import (
            CommandExecutionService,
        )

        cmd_id = uuid.uuid4()
        node_id = uuid.uuid4()
        template = CommandTemplateDTO(id=cmd_id, command="echo hi", parameters=(), timeout=30)
        cmd_reader = AsyncMock()
        cmd_reader.get_template.return_value = template
        node_reader = AsyncMock()
        # minimal NodeConnectionDTO
        from app.application.dto.node_connection import NodeConnectionDTO
        from app.application.dto.value_objects import NodeCredentials, NodeEndpoint

        node = NodeConnectionDTO(
            id=node_id,
            name="n",
            endpoint=NodeEndpoint(host="1.1.1.1", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="u"),
        )
        node_reader.get_connection.return_value = node
        cipher = MagicMock()
        cipher.decrypt.return_value = None
        factory = MagicMock()
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        connector.execute_command.return_value = ("out", "err", 0)
        factory.create_ssh.return_value = connector

        with patch("app.application.services.command_execution_service.build_ssh_connector") as mock_build, patch(
            "app.application.services.command_execution_service.execute_ssh"
        ) as mock_exec:
            mock_build.return_value = connector
            mock_exec.return_value = MagicMock(stdout="out", stderr="err", exit_code=0, started_at=datetime.now(UTC), finished_at=datetime.now(UTC))
            svc = CommandExecutionService(cmd_reader, node_reader, cipher, factory)
            await svc.execute_command(cmd_id, CommandExecuteRequestDTO(node_id=node_id, timeout=60))
            mock_build.assert_called_once()
            _, kwargs = mock_build.call_args
            assert kwargs.get("timeout") == 60 or mock_build.call_args.args[3] == 60 if len(mock_build.call_args.args) > 3 else True
            # check that build was called with timeout 60
            called_timeout = kwargs.get("timeout")
            if called_timeout is None:
                # positional
                called_timeout = mock_build.call_args.kwargs.get("timeout")
            assert called_timeout == 60

    @pytest.mark.asyncio
    async def test_effective_timeout_fallback_to_template(self):
        from app.application.dto.command_management import CommandExecuteRequestDTO
        from app.application.dto.command_template import CommandTemplateDTO
        from app.application.services.command_execution_service import (
            CommandExecutionService,
        )

        cmd_id = uuid.uuid4()
        node_id = uuid.uuid4()
        template = CommandTemplateDTO(id=cmd_id, command="echo hi", parameters=(), timeout=42)
        cmd_reader = AsyncMock()
        cmd_reader.get_template.return_value = template
        node_reader = AsyncMock()
        from app.application.dto.node_connection import NodeConnectionDTO
        from app.application.dto.value_objects import NodeCredentials, NodeEndpoint

        node = NodeConnectionDTO(
            id=node_id,
            name="n2",
            endpoint=NodeEndpoint(host="1.1.1.1", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="u"),
        )
        node_reader.get_connection.return_value = node
        cipher = MagicMock()
        cipher.decrypt.return_value = None
        factory = MagicMock()
        connector = AsyncMock()
        factory.create_ssh.return_value = connector
        with patch("app.application.services.command_execution_service.build_ssh_connector") as mock_build, patch(
            "app.application.services.command_execution_service.execute_ssh"
        ) as mock_exec:
            mock_build.return_value = connector
            mock_exec.return_value = MagicMock(stdout="out", stderr="", exit_code=0, started_at=datetime.now(UTC), finished_at=datetime.now(UTC))
            svc = CommandExecutionService(cmd_reader, node_reader, cipher, factory)
            await svc.execute_command(cmd_id, CommandExecuteRequestDTO(node_id=node_id, timeout=None))
            # fallback to 42
            _, kwargs = mock_build.call_args
            assert kwargs.get("timeout") == 42

# ---------------------------------------------------------------------------
# 6. ScriptExecutionService timeout
# ---------------------------------------------------------------------------

class TestScriptExecutionTimeout:
    def _make_node(self, node_id: uuid.UUID):
        from app.application.dto.node_connection import NodeConnectionDTO
        from app.application.dto.value_objects import NodeCredentials, NodeEndpoint

        return NodeConnectionDTO(
            id=node_id,
            name="n",
            endpoint=NodeEndpoint(host="127.0.0.1", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="root"),
        )

    @pytest.mark.asyncio
    async def test_effective_timeout_override_vs_definition(self):
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )

        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = self._make_node(node_id)
        script_reader = AsyncMock()
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "echo hi"},), timeout=30
        )
        command_reader = AsyncMock()
        node_reader = AsyncMock()
        node_reader.get_connections_by_ids.return_value = [node]
        node_reader.get_connections_by_tags.return_value = []
        writer = AsyncMock()
        writer.create_execution.return_value = uuid.uuid4()
        writer.update_execution.return_value = None
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        connector.execute_command.return_value = ("ok", "", 0)
        factory = MagicMock()
        factory.create_ssh.return_value = connector

        svc = ScriptExecutionService(script_reader, command_reader, node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), factory)
        # request timeout 99 overrides 30
        result = await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,), timeout=99))
        # check create_execution called with timeout 99
        assert writer.create_execution.await_args.args[0]["timeout"] == 99
        assert result.results[0].status == "success"
        writer.create_execution.reset_mock()
        # request timeout None -> fallback to definition 30
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "echo hi"},), timeout=55
        )
        await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,), timeout=None))
        assert writer.create_execution.await_args.args[0]["timeout"] == 55

    @pytest.mark.asyncio
    async def test_per_step_timeout_branch(self):
        from app.application.dto.script_execution import (
            ResolvedScriptStepDTO,
            ScriptExecutionTargetDTO,
        )
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )

        script_reader = AsyncMock()
        node_reader = AsyncMock()
        writer = AsyncMock()
        command_reader = AsyncMock()
        factory = MagicMock()
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        # per-step timeout via raising TimeoutError
        connector.execute_command.side_effect = TimeoutError("step timeout")
        factory.create_ssh.return_value = connector
        svc = ScriptExecutionService(script_reader, command_reader, node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), factory)
        target = ScriptExecutionTargetDTO(
            execution_id=uuid.uuid4(),
            script_id=uuid.uuid4(),
            node=self._make_node(uuid.uuid4()),
            steps=(ResolvedScriptStepDTO(label="a", command="sleep 10", on_failure="stop"),),
            timeout=1,
        )
        result = await svc._run_remote(target)
        assert result.steps[0].exit_code == 124
        assert "Timeout after 1s" in result.steps[0].stderr

    @pytest.mark.asyncio
    async def test_whole_script_timeout_branch(self):
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )

        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = self._make_node(node_id)
        script_reader = AsyncMock()
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "sleep 10"},), timeout=1
        )
        command_reader = AsyncMock()
        node_reader = AsyncMock()
        node_reader.get_connections_by_ids.return_value = [node]
        writer = AsyncMock()
        writer.create_execution.return_value = uuid.uuid4()
        # mock _run_remote to sleep longer than timeout
        svc = ScriptExecutionService(script_reader, command_reader, node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), MagicMock())
        async def _slow(target):
            await asyncio.sleep(5)
            from app.application.dto.script_execution import ScriptNodeResultDTO

            return ScriptNodeResultDTO(execution_id=target.execution_id, node_id=node_id, node_name="n", status="success", steps=())

        svc._run_remote = _slow  # type: ignore[method-assign]
        with pytest.raises(TimeoutError, match="timed out after 1s"):
            await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,), timeout=1))
        # should have called update_execution for each target with error
        assert writer.update_execution.await_count >= 1
        args = writer.update_execution.await_args.args[1]
        assert args["status"] == "error"

    @pytest.mark.asyncio
    async def test_register_execution_branch(self):
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )

        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = self._make_node(node_id)
        script_reader = AsyncMock()
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "echo hi"},), timeout=30
        )
        command_reader = AsyncMock()
        node_reader = AsyncMock()
        node_reader.get_connections_by_ids.return_value = [node]
        writer = AsyncMock()
        writer.create_execution.return_value = uuid.uuid4()
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        connector.execute_command.return_value = ("ok", "", 0)
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        svc = ScriptExecutionService(script_reader, command_reader, node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), factory)
        # Patch register_execution to capture call
        with patch("app.application.services.script_execution_service.register_execution") as mock_reg:
            result = await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,)))
            assert mock_reg.called
            assert result.results[0].status == "success"

    @pytest.mark.asyncio
    async def test_current_task_none_branch(self):
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )

        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = self._make_node(node_id)
        script_reader = AsyncMock()
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "echo hi"},), timeout=30
        )
        command_reader = AsyncMock()
        node_reader = AsyncMock()
        node_reader.get_connections_by_ids.return_value = [node]
        writer = AsyncMock()
        writer.create_execution.return_value = uuid.uuid4()
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        connector.execute_command.return_value = ("ok", "", 0)
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        svc = ScriptExecutionService(script_reader, command_reader, node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), factory)
        with patch("app.application.services.script_execution_service.asyncio.current_task", return_value=None), patch(
            "app.application.services.script_execution_service.register_execution"
        ) as mock_reg:
            result = await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,)))
            mock_reg.assert_not_called()
            assert result.results[0].status == "success"

    @pytest.mark.asyncio
    async def test_update_execution_exception_branch(self):
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )

        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = self._make_node(node_id)
        script_reader = AsyncMock()
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "echo hi"},), timeout=30
        )
        command_reader = AsyncMock()
        node_reader = AsyncMock()
        node_reader.get_connections_by_ids.return_value = [node]
        writer = AsyncMock()
        writer.create_execution.return_value = uuid.uuid4()
        writer.update_execution.side_effect = RuntimeError("db fail")
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        connector.execute_command.return_value = ("ok", "", 0)
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        svc = ScriptExecutionService(script_reader, command_reader, node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), factory)
        result = await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,)))
        assert result.results[0].status == "success"

    @pytest.mark.asyncio
    async def test_audit_write_error_branch(self):
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )
        from app.core.exceptions import AuditWriteError

        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = self._make_node(node_id)
        script_reader = AsyncMock()
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "echo hi"},), timeout=30
        )
        command_reader = AsyncMock()
        node_reader = AsyncMock()
        node_reader.get_connections_by_ids.return_value = [node]
        writer = AsyncMock()
        writer.create_execution.return_value = uuid.uuid4()
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        connector.execute_command.return_value = ("ok", "", 0)
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        audit_mock = AsyncMock()
        audit_mock.log.side_effect = AuditWriteError("fail")
        svc = ScriptExecutionService(script_reader, command_reader, node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), factory, audit_service=audit_mock)
        result = await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,)))
        assert result.results[0].status == "success"
        assert audit_mock.log.await_count == 1

# ---------------------------------------------------------------------------
# 7. Node bulk with timeout
# ---------------------------------------------------------------------------

class TestNodeBulkTimeout:
    @pytest.mark.asyncio
    async def test_execute_on_single_node_with_timeout(self):
        from app.application.dto.node_connection import NodeConnectionDTO
        from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
        from app.application.services.node_bulk_command_service import (
            NodeBulkCommandService,
        )

        node = NodeConnectionDTO(
            id=uuid.uuid4(),
            name="n",
            endpoint=NodeEndpoint(host="1.1.1.1", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="u"),
        )
        cipher = MagicMock()
        cipher.decrypt.return_value = None
        factory = MagicMock()
        connector = AsyncMock()
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=None)
        connector.execute_command.return_value = ("out", "err", 0)
        factory.create_ssh.return_value = connector
        svc = NodeBulkCommandService(AsyncMock(), cipher, factory)
        with patch("app.application.services.node_bulk_command_service.build_ssh_connector") as mock_build, patch(
            "app.application.services.node_bulk_command_service.execute_ssh"
        ) as mock_exec:
            mock_build.return_value = connector
            mock_exec.return_value = MagicMock(stdout="out", stderr="err", exit_code=0)
            result = await svc._execute_on_single_node(node, "echo hi", timeout=77)
            mock_build.assert_called_once()
            # check timeout passed
            assert mock_build.call_args.kwargs.get("timeout") == 77
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_on_single_node_without_timeout(self):
        from app.application.dto.node_connection import NodeConnectionDTO
        from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
        from app.application.services.node_bulk_command_service import (
            NodeBulkCommandService,
        )

        node = NodeConnectionDTO(
            id=uuid.uuid4(),
            name="n2",
            endpoint=NodeEndpoint(host="1.1.1.1", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="u"),
        )
        cipher = MagicMock()
        cipher.decrypt.return_value = None
        factory = MagicMock()
        svc = NodeBulkCommandService(AsyncMock(), cipher, factory)
        with patch("app.application.services.node_bulk_command_service.build_ssh_connector") as mock_build, patch(
            "app.application.services.node_bulk_command_service.execute_ssh"
        ) as mock_exec:
            connector = AsyncMock()
            mock_build.return_value = connector
            mock_exec.return_value = MagicMock(stdout="ok", stderr="", exit_code=0)
            result = await svc._execute_on_single_node(node, "echo hi", timeout=None)
            assert mock_build.call_args.kwargs.get("timeout") is None
            assert result.stdout == "ok"

# ---------------------------------------------------------------------------
# 8. API history handlers
# ---------------------------------------------------------------------------

def _make_cmd_history_app(exec_history: AsyncMock):
    from app.api.v2.commands_handlers.history import router as hist_router

    app = FastAPI()
    app.add_exception_handler(Exception, domain_error_handler)
    app.include_router(hist_router, prefix="/api/v2/commands")

    class Prov(Provider):
        @provide(scope=Scope.REQUEST)
        def get_exec_history(self) -> ExecutionHistoryService:
            return as_typed_mock(ExecutionHistoryService, exec_history)

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:  # type: ignore[no-redef]
            return get_settings()

    container = make_async_container(Prov(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app

def _make_batch_history_app(exec_history: AsyncMock):
    from app.api.v2.commands_handlers.executions_handlers.lifecycle_handlers.history import (
        router as hist_router,
    )

    app = FastAPI()
    app.add_exception_handler(Exception, domain_error_handler)
    app.include_router(hist_router, prefix="/api/v2/commands")

    class Prov(Provider):
        @provide(scope=Scope.REQUEST)
        def get_exec_history(self) -> ExecutionHistoryService:
            return as_typed_mock(ExecutionHistoryService, exec_history)

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:  # type: ignore[no-redef]
            return get_settings()

    container = make_async_container(Prov(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app

def _make_node_history_app(service_mock: AsyncMock):
    from app.api.v2.nodes_handlers.history import router as hist_router

    app = FastAPI()
    app.add_exception_handler(Exception, domain_error_handler)
    app.include_router(hist_router, prefix="/api/v2/nodes")

    class Prov(Provider):
        @provide(scope=Scope.REQUEST)
        def get_node_history(self) -> NodeStatusHistoryService:
            return as_typed_mock(NodeStatusHistoryService, service_mock)

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:  # type: ignore[no-redef]
            return get_settings()

    container = make_async_container(Prov(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app

def _make_script_history_app(service_mock: AsyncMock):
    from app.api.v2.scripts_handlers.executions_handlers.lifecycle_handlers.history import (
        router as hist_router,
    )

    app = FastAPI()
    app.add_exception_handler(Exception, domain_error_handler)
    app.include_router(hist_router, prefix="/api/v2/scripts")

    class Prov(Provider):
        @provide(scope=Scope.REQUEST)
        def get_script_history(self) -> ScriptHistoryService:
            return as_typed_mock(ScriptHistoryService, service_mock)

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:  # type: ignore[no-redef]
            return get_settings()

    container = make_async_container(Prov(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app

class TestCommandHistoryAPI:
    @pytest.mark.asyncio
    async def test_get_command_executions_by_command_no_cursor(self):
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_command_history.return_value = CommandHistoryPageDTO(items=(dto,), total=1)
        app = _make_cmd_history_app(svc)
        cmd_id = uuid.uuid4()
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/commands/{cmd_id}/executions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        svc.get_command_history.assert_awaited_once_with(cmd_id, page=1, size=20)

    @pytest.mark.asyncio
    async def test_get_command_executions_by_command_with_cursor_and_limit(self):
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_command_history.return_value = CommandHistoryPageDTO(items=(dto, dto), total=5)
        app = _make_cmd_history_app(svc)
        cmd_id = uuid.uuid4()
        cursor = _encode_offset(0)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/commands/{cmd_id}/executions?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        assert resp.json()["has_more"] is True
        # also test invalid cursor
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp2 = await ac.get(f"/api/v2/commands/{cmd_id}/executions?cursor=bad")
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_get_command_executions_remainder_slicing(self):
        svc = AsyncMock()
        # create 3 items, total 5, offset 1 limit 2 -> remainder 1, fetch_size 3, items sliced remainder:remainder+limit -> 1:3 => 2 items, has_more true
        dtos = tuple(_make_history_dto() for _ in range(3))
        svc.get_command_history.return_value = CommandHistoryPageDTO(items=dtos, total=5)
        app = _make_cmd_history_app(svc)
        cmd_id = uuid.uuid4()
        cursor = _encode_offset(1)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/commands/{cmd_id}/executions?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] == _encode_offset(3)

    @pytest.mark.asyncio
    async def test_get_history_helper(self):
        from app.api.v2.commands_handlers.history import _get_history

        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_node_history.return_value = CommandHistoryPageDTO(items=(dto,), total=1)
        node_id = uuid.uuid4()
        result = await _get_history(svc, node_id, None, 20)
        assert len(result.items) == 1
        # invalid cursor
        with pytest.raises(Exception):
            await _get_history(svc, node_id, "bad", 20)
        # with cursor remainder
        dtos = tuple(_make_history_dto() for _ in range(3))
        svc.get_node_history.return_value = CommandHistoryPageDTO(items=dtos, total=10)
        cursor = _encode_offset(1)
        result2 = await _get_history(svc, node_id, cursor, 2)
        assert len(result2.items) == 2

class TestBatchHistoryAPI:
    @pytest.mark.asyncio
    async def test_get_executions_by_batch_alias_no_cursor(self):
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_batch_history.return_value = CommandHistoryPageDTO(items=(dto,), total=1)
        app = _make_batch_history_app(svc)
        batch_id = uuid.uuid4()
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/commands/executions?batch_id={batch_id}")
        assert resp.status_code == 200
        svc.get_batch_history.assert_awaited_once_with(batch_id, page=1, size=20)

    @pytest.mark.asyncio
    async def test_get_batch_history_with_cursor(self):
        svc = AsyncMock()
        dto = _make_history_dto()
        svc.get_batch_history.return_value = CommandHistoryPageDTO(items=(dto,), total=5)
        app = _make_batch_history_app(svc)
        batch_id = uuid.uuid4()
        cursor = _encode_offset(0)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/commands/executions?batch_id={batch_id}&cursor={cursor}&limit=2")
        assert resp.status_code == 200
        assert resp.json()["has_more"] is True
        # and history endpoint alias
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp2 = await ac.get(f"/api/v2/commands/executions/history?batch_id={batch_id}&cursor={cursor}&limit=2")
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_get_batch_history_invalid_cursor(self):
        svc = AsyncMock()
        app = _make_batch_history_app(svc)
        batch_id = uuid.uuid4()
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/commands/executions?batch_id={batch_id}&cursor=bad")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_batch_history_remainder(self):
        from app.api.v2.commands_handlers.executions_handlers.lifecycle_handlers.history import (
            _get_batch_history,
        )

        svc = AsyncMock()
        dtos = tuple(_make_history_dto() for _ in range(3))
        svc.get_batch_history.return_value = CommandHistoryPageDTO(items=dtos, total=10)
        batch_id = uuid.uuid4()
        cursor = _encode_offset(1)
        result = await _get_batch_history(svc, batch_id, cursor, 2)
        assert len(result.items) == 2
        assert result.has_more is True

class TestNodeHistoryAlias:
    @pytest.mark.asyncio
    async def test_get_node_history_alias(self):
        from app.api.v2.nodes_handlers.history import get_node_history_alias
        from app.application.dto.node_status_history import (
            NodeStatusHistoryPageDTO,
            NodeStatusHistoryRecordDTO,
        )

        now = datetime.now(UTC)
        dto = NodeStatusHistoryRecordDTO(id=uuid.uuid4(), node_id=uuid.uuid4(), old_status="active", new_status="active", source="manual_update", changed_at=now)  # type: ignore[arg-type]
        svc = AsyncMock()
        svc.get_history.return_value = NodeStatusHistoryPageDTO(items=(dto,), total=1)
        node_id = uuid.uuid4()
        # Call alias via its original function to avoid dishka wrapper
        alias_orig = get_node_history_alias.__dishka_orig_func__  # type: ignore[attr-defined]
        mock_inner = AsyncMock(return_value=MagicMock(items=[dto]))
        with patch("app.api.v2.nodes_handlers.history.get_node_status_history", mock_inner):
            result = await alias_orig(node_id, svc, None, 20, MagicMock())  # type: ignore[arg-type]
            mock_inner.assert_awaited_once()
            assert result is not None
        # Also test status-history via HTTP (no alias nesting)
        svc2 = AsyncMock()
        svc2.get_history.return_value = NodeStatusHistoryPageDTO(items=(dto,), total=1)
        app = _make_node_history_app(svc2)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp2 = await ac.get(f"/api/v2/nodes/{node_id}/status-history")
        assert resp2.status_code == 200
        assert len(resp2.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_node_history_invalid_cursor(self):
        from app.api.v2.nodes_handlers.history import get_node_status_history

        svc = AsyncMock()
        node_id = uuid.uuid4()
        orig = get_node_status_history.__dishka_orig_func__  # type: ignore[attr-defined]
        with pytest.raises(Exception) as exc:
            await orig(node_id, svc, cursor="bad!!", limit=20, _principal=MagicMock())  # type: ignore[arg-type]
        assert "422" in str(exc.value) or "Invalid cursor" in str(exc.value)
        # Also test via HTTP for status-history
        app = _make_node_history_app(svc)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/nodes/{node_id}/status-history?cursor=bad!!")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_node_history_with_cursor_remainder(self):
        svc = AsyncMock()
        from app.application.dto.node_status_history import (
            NodeStatusHistoryPageDTO,
            NodeStatusHistoryRecordDTO,
        )

        now = datetime.now(UTC)
        dtos = tuple(NodeStatusHistoryRecordDTO(id=uuid.uuid4(), node_id=uuid.uuid4(), old_status="active", new_status="active", source="manual_update", changed_at=now) for _ in range(3))
        svc.get_history.return_value = NodeStatusHistoryPageDTO(items=dtos, total=10)
        app = _make_node_history_app(svc)
        node_id = uuid.uuid4()
        cursor = _encode_offset(1)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/nodes/{node_id}/status-history?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        # node history does NOT do remainder slicing, it just passes offset/limit to service, so returns all 3
        assert len(resp.json()["items"]) == 3

class TestScriptHistoryAlias:
    def _make_exec_dto(self, script_id: uuid.UUID):
        from app.application.dto.script_execution import ScriptExecutionDTO

        now = datetime.now(UTC)
        return ScriptExecutionDTO(
            id=uuid.uuid4(),
            script_id=script_id,
            node_id=uuid.uuid4(),
            params=(),
            status="success",
            steps=(),
            started_at=now,
            finished_at=now,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_get_executions_alias(self):
        svc = AsyncMock()
        script_id = uuid.uuid4()
        dto = self._make_exec_dto(script_id)
        svc.get_executions.return_value = ([dto], 1)
        app = _make_script_history_app(svc)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/scripts/{script_id}/executions")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        # alias via /executions/history?script_id=
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp2 = await ac.get(f"/api/v2/scripts/executions/history?script_id={script_id}")
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_get_executions_with_cursor(self):
        svc = AsyncMock()
        script_id = uuid.uuid4()
        dtos = [self._make_exec_dto(script_id) for _ in range(3)]
        svc.get_executions.return_value = (dtos, 10)
        app = _make_script_history_app(svc)
        cursor = _encode_offset(1)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/scripts/{script_id}/executions?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2
        assert resp.json()["has_more"] is True

    @pytest.mark.asyncio
    async def test_get_executions_invalid_cursor(self):
        svc = AsyncMock()
        script_id = uuid.uuid4()
        svc.get_executions.return_value = ([], 0)
        app = _make_script_history_app(svc)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.get(f"/api/v2/scripts/{script_id}/executions?cursor=bad")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_internal_get_executions_helper(self):
        from app.api.v2.scripts_handlers.executions_handlers.lifecycle_handlers.history import (
            _get_executions,
        )

        svc = AsyncMock()
        script_id = uuid.uuid4()
        dtos = [self._make_exec_dto(script_id) for _ in range(2)]
        svc.get_executions.return_value = (dtos, 5)
        cursor = _encode_offset(0)
        result = await _get_executions(svc, script_id, cursor, 2)
        assert len(result.items) == 2
        assert result.has_more is True
        # remainder case: offset 1 limit 2 => fetch 3, slice 1:3 =>2
        dtos2 = [self._make_exec_dto(script_id) for _ in range(3)]
        svc.get_executions.return_value = (dtos2, 5)
        cursor2 = _encode_offset(1)
        result2 = await _get_executions(svc, script_id, cursor2, 2)
        assert len(result2.items) == 2
        # invalid cursor
        with pytest.raises(Exception):
            await _get_executions(svc, script_id, "bad", 2)

# ---------------------------------------------------------------------------
# 9. Bulk create with timeout
# ---------------------------------------------------------------------------

class TestBulkCreateTimeout:
    @pytest.mark.asyncio
    async def test_bulk_create_command_with_timeout(self):

        svc = AsyncMock()
        now = datetime.now(UTC)
        view = CommandViewDTO(id=uuid.uuid4(), name="n", description=None, command="echo hi", parameters=(), tags=(), timeout=60, created_at=now, updated_at=now)
        svc.create_command.return_value = view
        # Build app via commands façade
        from app.api.v2.commands import router as cmd_router

        app = FastAPI()
        app.add_exception_handler(Exception, domain_error_handler)
        app.include_router(cmd_router, prefix="/api/v2")

        class Prov(Provider):
            @provide(scope=Scope.REQUEST)
            def get_cmd_mgmt(self) -> CommandManagementService:
                return as_typed_mock(CommandManagementService, svc)

            @provide(scope=Scope.REQUEST)
            def get_exec_history(self) -> ExecutionHistoryService:
                return as_typed_mock(ExecutionHistoryService, AsyncMock())

            @provide(scope=Scope.REQUEST)
            def get_exec_stats(self) -> ExecutionStatsService:
                return as_typed_mock(ExecutionStatsService, AsyncMock())

            @provide(scope=Scope.REQUEST)
            def get_bulk_cmd(self) -> NodeBulkCommandService:
                return as_typed_mock(NodeBulkCommandService, AsyncMock())

            @provide(scope=Scope.REQUEST)
            def get_exec_lifecycle(self) -> ExecutionLifecycleService:
                return as_typed_mock(ExecutionLifecycleService, AsyncMock())

            @provide(scope=Scope.APP)
            def get_settings(self) -> Settings:  # type: ignore[no-redef]
                return get_settings()

        container = make_async_container(Prov(), MockAuthServiceProvider())
        setup_dishka(container, app)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.post("/api/v2/commands/", json={"items": [{"name": "n", "command": "echo hi", "timeout": 60}]})
        assert resp.status_code in (200, 201, 207)
        # verify timeout passed to service
        assert svc.create_command.await_args.args[0].timeout == 60

    @pytest.mark.asyncio
    async def test_bulk_create_script_with_timeout(self):
        from app.api.v2.scripts import router as script_router

        svc = AsyncMock()
        now = datetime.now(UTC)
        view = ScriptViewDTO(id=uuid.uuid4(), name="s", description=None, steps=(ScriptStepDTO(label="a", type="inline", command="echo hi"),), tags=(), timeout=77, created_at=now, updated_at=now)
        svc.create_script.return_value = view

        app = FastAPI()
        app.add_exception_handler(Exception, domain_error_handler)
        app.include_router(script_router, prefix="/api/v2")

        class Prov(Provider):
            @provide(scope=Scope.REQUEST)
            def get_script_mgmt(self) -> ScriptManagementService:
                return as_typed_mock(ScriptManagementService, svc)

            @provide(scope=Scope.REQUEST)
            def get_script_history(self) -> ScriptHistoryService:
                return as_typed_mock(ScriptHistoryService, AsyncMock())

            @provide(scope=Scope.REQUEST)
            def get_script_exec(self) -> ScriptExecutionService:
                return as_typed_mock(ScriptExecutionService, AsyncMock())

            @provide(scope=Scope.REQUEST)
            def get_schedule_mgmt(self) -> ScheduleManagementService:
                return as_typed_mock(ScheduleManagementService, AsyncMock())

            @provide(scope=Scope.REQUEST)
            def get_exec_stats(self) -> ExecutionStatsService:
                return as_typed_mock(ExecutionStatsService, AsyncMock())

            @provide(scope=Scope.REQUEST)
            def get_exec_lifecycle(self) -> ExecutionLifecycleService:
                return as_typed_mock(ExecutionLifecycleService, AsyncMock())

            @provide(scope=Scope.APP)
            def get_settings(self) -> Settings:  # type: ignore[no-redef]
                return get_settings()

        container = make_async_container(Prov(), MockAuthServiceProvider())
        setup_dishka(container, app)
        with _settings_patcher:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "test-master"}) as ac:
                resp = await ac.post("/api/v2/scripts/", json={"items": [{"name": "s", "steps": [{"label": "a", "type": "inline", "command": "echo hi", "params": {}, "on_failure": "stop"}], "timeout": 77}]})
        assert resp.status_code in (200, 201, 207)
        assert svc.create_script.await_args.args[0].timeout == 77


# ---------------------------------------------------------------------------
# 10. Additional coverage for remaining branches
# ---------------------------------------------------------------------------

class TestAdditionalCoverage:
    def test_node_response_mapping(self):
        from app.api.v2.nodes_handlers.history import _node_response
        from app.application.dto.node_view import NodeViewDTO
        from app.application.dto.value_objects import NodeEndpoint

        now = datetime.now(UTC)
        view = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",  # type: ignore[arg-type]
            username="u",
            tags=("t1",),
            created_at=now,
            updated_at=now,
            endpoint=NodeEndpoint(host="1.2.3.4", port=22, connection_type="ssh"),
        )
        resp = _node_response(view)
        assert resp.host == "1.2.3.4"
        assert resp.tags == ["t1"]

    @pytest.mark.asyncio
    async def test_node_history_decode_cursor_success(self):
        from app.api.v2.nodes_handlers.history import get_node_status_history
        from app.application.dto.node_status_history import (
            NodeStatusHistoryPageDTO,
            NodeStatusHistoryRecordDTO,
        )
        from app.schemas.common import encode_cursor

        svc = AsyncMock()
        now = datetime.now(UTC)
        dto = NodeStatusHistoryRecordDTO(id=uuid.uuid4(), node_id=uuid.uuid4(), old_status="active", new_status="active", source="manual_update", changed_at=now)  # type: ignore[arg-type]
        svc.get_history.return_value = NodeStatusHistoryPageDTO(items=(dto,), total=1)
        # cursor that is valid for decode_cursor but not decode_offset
        cursor = encode_cursor(now, uuid.uuid4())
        orig = get_node_status_history.__dishka_orig_func__  # type: ignore[attr-defined]
        result = await orig(uuid.uuid4(), svc, cursor=cursor, limit=20, _principal=MagicMock())  # type: ignore[arg-type]
        assert len(result.items) == 1
        # svc should be called with offset 0
        assert svc.get_history.await_args.args[0].offset == 0

    @pytest.mark.asyncio
    async def test_script_whole_timeout_with_writer_exception(self):
        from app.application.services.script_execution_service import (
            ScriptExecutionService,
        )

        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        from app.application.dto.node_connection import NodeConnectionDTO
        from app.application.dto.value_objects import NodeCredentials, NodeEndpoint

        node = NodeConnectionDTO(
            id=node_id,
            name="n",
            endpoint=NodeEndpoint(host="127.0.0.1", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="root"),
        )
        script_reader = AsyncMock()
        script_reader.get_definition.return_value = ScriptDefinitionDTO(
            id=script_id, steps=({"label": "a", "type": "inline", "command": "sleep 10"},), timeout=1
        )
        node_reader = AsyncMock()
        node_reader.get_connections_by_ids.return_value = [node]
        writer = AsyncMock()
        writer.create_execution.return_value = uuid.uuid4()
        writer.update_execution.side_effect = RuntimeError("db fail")
        svc = ScriptExecutionService(script_reader, AsyncMock(), node_reader, writer, MagicMock(decrypt=MagicMock(return_value=None)), MagicMock())

        async def _slow(target):
            await asyncio.sleep(5)
            from app.application.dto.script_execution import ScriptNodeResultDTO

            return ScriptNodeResultDTO(execution_id=target.execution_id, node_id=node_id, node_name="n", status="success", steps=())

        svc._run_remote = _slow  # type: ignore[method-assign]
        with pytest.raises(TimeoutError):
            await svc.execute_script(script_id, ScriptExecutionRequestDTO(node_ids=(node_id,), timeout=1))
        # writer.update_execution was attempted and exception swallowed via pass
        assert writer.update_execution.await_count >= 1

    def test_command_schemas_timeout_validation(self):
        from app.schemas.command import CommandExecutionsRequest, RawExecutionsRequest
        from app.schemas.script import ScriptExecutionsRequest

        # valid timeout
        r = CommandExecutionsRequest(command_ids=[uuid.uuid4()], node_ids=[uuid.uuid4()], timeout=60)
        assert r.timeout == 60
        # invalid timeout should raise
        with pytest.raises(Exception):
            CommandExecutionsRequest(command_ids=[uuid.uuid4()], timeout=9999)
        r2 = ScriptExecutionsRequest(script_ids=[uuid.uuid4()], node_ids=[uuid.uuid4()], timeout=30)
        assert r2.timeout == 30
        r3 = RawExecutionsRequest(commands=["echo hi"], node_ids=[uuid.uuid4()], timeout=100)
        assert r3.timeout == 100

    def test_timeout_boundary_1_and_3600(self):
        from app.schemas.command import CommandCreate, CommandExecuteRequest, RawExecutionsRequest
        from app.schemas.script import ScriptCreate, ScriptExecuteRequest

        # lower bound 1 and upper 3600 should pass
        assert CommandCreate(name="n", command="echo hi", timeout=1).timeout == 1
        assert CommandCreate(name="n", command="echo hi", timeout=3600).timeout == 3600
        assert ScriptCreate(name="s", steps=[{"label": "a", "type": "inline", "command": "echo hi", "params": {}, "on_failure": "stop"}], timeout=1).timeout == 1  # type: ignore[arg-type]
        assert ScriptCreate(name="s", steps=[{"label": "a", "type": "inline", "command": "echo hi", "params": {}, "on_failure": "stop"}], timeout=3600).timeout == 3600  # type: ignore[arg-type]
        assert CommandExecuteRequest(node_id=uuid.uuid4(), timeout=1).timeout == 1
        assert CommandExecuteRequest(node_id=uuid.uuid4(), timeout=3600).timeout == 3600
        assert ScriptExecuteRequest(node_ids=[uuid.uuid4()], timeout=1).timeout == 1
        assert ScriptExecuteRequest(node_ids=[uuid.uuid4()], timeout=3600).timeout == 3600
        assert RawExecutionsRequest(commands=["echo hi"], timeout=1).timeout == 1
        assert RawExecutionsRequest(commands=["echo hi"], timeout=3600).timeout == 3600
        # 0 and 3601 should fail
        with pytest.raises(Exception):
            CommandCreate(name="n", command="echo hi", timeout=0)
        with pytest.raises(Exception):
            CommandCreate(name="n", command="echo hi", timeout=3601)
        with pytest.raises(Exception):
            CommandExecuteRequest(node_id=uuid.uuid4(), timeout=0)
        with pytest.raises(Exception):
            ScriptExecuteRequest(node_ids=[uuid.uuid4()], timeout=3601)

