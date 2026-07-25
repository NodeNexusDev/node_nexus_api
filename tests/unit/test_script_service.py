"""Unit tests for ScriptService."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import (
    CommandNotFoundError,
    ScriptNotFoundError,
    TemplateRenderError,
)
from app.repositories.command_repo import CommandRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository
from app.schemas.script import (
    ScriptCreate,
    ScriptExecuteRequest,
    ScriptStep,
    ScriptUpdate,
)
from app.services.script_service import ScriptService
from tests.unit.conftest import make_orm_command, make_orm_node


def _make_orm_script(**overrides: Any) -> Any:
    from app.models.script import ScriptModel

    steps = [
        {
            "label": "Check disk",
            "type": "inline",
            "command": "df -h",
            "on_failure": "stop",
        }
    ]
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "deploy_check",
        "description": "Pre-deploy check",
        "steps": steps,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ScriptModel(**defaults)


def _make_orm_execution(**overrides: Any) -> Any:
    from app.models.script_execution import ScriptExecutionModel

    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "script_id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "params": {"key": "value"},
        "status": "completed",
        "steps": [
            {
                "step_index": 0,
                "label": "Step 1",
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
            }
        ],
        "started_at": datetime.now(UTC),
        "finished_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ScriptExecutionModel(**defaults)


@pytest.fixture
def script_repo() -> AsyncMock:
    return AsyncMock(spec=ScriptRepository)


@pytest.fixture
def cmd_repo() -> AsyncMock:
    return AsyncMock(spec=CommandRepository)


@pytest.fixture
def node_repo() -> AsyncMock:
    return AsyncMock(spec=NodeRepository)


@pytest.fixture
def exec_repo() -> AsyncMock:
    return AsyncMock(spec=ScriptExecutionRepository)


@pytest.fixture
def service(
    script_repo: AsyncMock,
    cmd_repo: AsyncMock,
    node_repo: AsyncMock,
    exec_repo: AsyncMock,
) -> ScriptService:
    return ScriptService(
        repository=script_repo,
        command_repository=cmd_repo,
        node_repository=node_repo,
        execution_repository=exec_repo,
    )


class TestGetScript:
    async def test_found(self, service: ScriptService, script_repo: AsyncMock) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script
        result = await service.get_script(orm_script.id)
        assert result.name == "deploy_check"
        assert len(result.steps) == 1

    async def test_not_found(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        script_repo.get_by_id.return_value = None
        with pytest.raises(ScriptNotFoundError):
            await service.get_script(uuid.uuid4())


class TestCreateScript:
    async def test_create(self, service: ScriptService, script_repo: AsyncMock) -> None:
        orm_script = _make_orm_script()
        script_repo.create.return_value = orm_script
        data = ScriptCreate(
            name="deploy_check",
            steps=[ScriptStep(label="Check disk", type="inline", command="df -h")],
        )
        result = await service.create_script(data)
        assert result.name == "deploy_check"
        script_repo.create.assert_called_once()


class TestDeleteScript:
    async def test_delete(self, service: ScriptService, script_repo: AsyncMock) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script
        script_repo.delete.return_value = True
        result = await service.delete_script(orm_script.id)
        assert result is True

    async def test_not_found(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        script_repo.get_by_id.return_value = None
        with pytest.raises(ScriptNotFoundError):
            await service.delete_script(uuid.uuid4())


class TestGetAllScripts:
    async def test_returns_list(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        orm_scripts = [_make_orm_script(), _make_orm_script()]
        script_repo.get_all.return_value = orm_scripts
        script_repo.count.return_value = 2
        scripts, total = await service.get_all_scripts()
        assert len(scripts) == 2
        assert total == 2

    async def test_empty_list(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        script_repo.get_all.return_value = []
        script_repo.count.return_value = 0
        scripts, total = await service.get_all_scripts()
        assert scripts == []
        assert total == 0


class TestUpdateScript:
    async def test_update_name(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        orm_script = _make_orm_script()
        script_repo.update.return_value = orm_script
        data = ScriptUpdate(name="new-name")
        result = await service.update_script(orm_script.id, data)
        assert result.name == "deploy_check"

    async def test_update_with_steps(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        new_steps = [ScriptStep(label="New step", type="inline", command="echo 1")]
        orm_script = _make_orm_script(
            steps=[s.model_dump(mode="json") for s in new_steps]
        )
        script_repo.update.return_value = orm_script
        data = ScriptUpdate(steps=new_steps)
        result = await service.update_script(orm_script.id, data)
        assert len(result.steps) == 1

    async def test_not_found(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        script_repo.update.return_value = None
        data = ScriptUpdate(name="x")
        with pytest.raises(ScriptNotFoundError):
            await service.update_script(uuid.uuid4(), data)


class TestGetExecutions:
    async def test_success(
        self,
        service: ScriptService,
        script_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script
        execution = _make_orm_execution(script_id=orm_script.id)
        exec_repo.get_by_script_id.return_value = [execution]
        exec_repo.count_by_script_id.return_value = 1
        executions, total = await service.get_executions(orm_script.id)
        assert total == 1
        assert executions[0].status == "completed"

    async def test_script_not_found(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        script_repo.get_by_id.return_value = None
        with pytest.raises(ScriptNotFoundError):
            await service.get_executions(uuid.uuid4())


class TestExecuteScript:
    async def test_success(
        self,
        service: ScriptService,
        script_repo: AsyncMock,
        node_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        execution = _make_orm_execution(script_id=orm_script.id, node_id=orm_node.id)
        exec_repo.create.return_value = execution
        exec_repo.update.return_value = execution

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)

        factory = Mock()
        factory.create_ssh.return_value = connector

        service_with_factory = ScriptService(
            repository=script_repo,
            command_repository=AsyncMock(),
            node_repository=node_repo,
            execution_repository=exec_repo,
            connector_factory=factory,
        )

        data = ScriptExecuteRequest(node_ids=[orm_node.id], params={})
        result = await service_with_factory.execute_script(orm_script.id, data)
        assert result.script_id == orm_script.id
        assert len(result.results) == 1
        assert result.results[0].status == "completed"

    async def test_script_not_found(
        self, service: ScriptService, script_repo: AsyncMock
    ) -> None:
        script_repo.get_by_id.return_value = None
        data = ScriptExecuteRequest(node_ids=[uuid.uuid4()], params={})
        with pytest.raises(ScriptNotFoundError):
            await service.execute_script(uuid.uuid4(), data)

    async def test_node_not_found(
        self,
        service: ScriptService,
        script_repo: AsyncMock,
        node_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script
        node_repo.get_by_id.return_value = None

        execution = _make_orm_execution(script_id=orm_script.id)
        exec_repo.create.return_value = execution
        exec_repo.update.return_value = execution

        factory = Mock()
        service_with_factory = ScriptService(
            repository=script_repo,
            command_repository=AsyncMock(),
            node_repository=node_repo,
            execution_repository=exec_repo,
            connector_factory=factory,
        )

        data = ScriptExecuteRequest(node_ids=[uuid.uuid4()], params={})
        result = await service_with_factory.execute_script(orm_script.id, data)
        assert result.results[0].status == "failed"

    async def test_connector_error(
        self,
        script_repo: AsyncMock,
        node_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        execution = _make_orm_execution(script_id=orm_script.id, node_id=orm_node.id)
        exec_repo.create.return_value = execution
        exec_repo.update.return_value = execution

        connector = AsyncMock()
        connector.connect = AsyncMock(side_effect=Exception("SSH error"))

        factory = Mock()
        factory.create_ssh.return_value = connector

        service = ScriptService(
            repository=script_repo,
            command_repository=AsyncMock(),
            node_repository=node_repo,
            execution_repository=exec_repo,
            connector_factory=factory,
        )

        data = ScriptExecuteRequest(node_ids=[orm_node.id], params={})
        result = await service.execute_script(orm_script.id, data)
        assert result.results[0].status == "failed"

    async def test_step_failure_stop(
        self,
        script_repo: AsyncMock,
        node_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        steps = [
            {
                "label": "Step 1",
                "type": "inline",
                "command": "exit 1",
                "on_failure": "stop",
            },
            {
                "label": "Step 2",
                "type": "inline",
                "command": "echo 2",
                "on_failure": "stop",
            },
        ]
        orm_script = _make_orm_script(steps=steps)
        script_repo.get_by_id.return_value = orm_script

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        execution = _make_orm_execution(script_id=orm_script.id, node_id=orm_node.id)
        exec_repo.create.return_value = execution
        exec_repo.update.return_value = execution

        connector = AsyncMock()
        connector.execute_command.return_value = ("", "error", 1)

        factory = Mock()
        factory.create_ssh.return_value = connector

        service = ScriptService(
            repository=script_repo,
            command_repository=AsyncMock(),
            node_repository=node_repo,
            execution_repository=exec_repo,
            connector_factory=factory,
        )

        data = ScriptExecuteRequest(node_ids=[orm_node.id], params={})
        result = await service.execute_script(orm_script.id, data)
        assert result.results[0].status == "failed"
        assert len(result.results[0].steps) == 1

    async def test_step_failure_continue(
        self,
        script_repo: AsyncMock,
        node_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        steps = [
            {
                "label": "Step 1",
                "type": "inline",
                "command": "exit 1",
                "on_failure": "continue",
            },
            {
                "label": "Step 2",
                "type": "inline",
                "command": "echo 2",
                "on_failure": "stop",
            },
        ]
        orm_script = _make_orm_script(steps=steps)
        script_repo.get_by_id.return_value = orm_script

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        execution = _make_orm_execution(script_id=orm_script.id, node_id=orm_node.id)
        exec_repo.create.return_value = execution
        exec_repo.update.return_value = execution

        connector = AsyncMock()
        connector.execute_command.side_effect = [
            ("", "error", 1),
            ("ok", "", 0),
        ]

        factory = Mock()
        factory.create_ssh.return_value = connector

        service = ScriptService(
            repository=script_repo,
            command_repository=AsyncMock(),
            node_repository=node_repo,
            execution_repository=exec_repo,
            connector_factory=factory,
        )

        data = ScriptExecuteRequest(node_ids=[orm_node.id], params={})
        result = await service.execute_script(orm_script.id, data)
        assert result.results[0].status == "completed"
        assert len(result.results[0].steps) == 2

    async def test_multi_node(
        self,
        script_repo: AsyncMock,
        node_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script

        node1 = make_orm_node(name="node-1")
        node2 = make_orm_node(name="node-2")
        node_repo.get_by_id.side_effect = [node1, node2]

        exec_repo.create.return_value = _make_orm_execution(
            script_id=orm_script.id, node_id=node1.id
        )
        exec_repo.update.return_value = _make_orm_execution()

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)

        factory = Mock()
        factory.create_ssh.return_value = connector

        service = ScriptService(
            repository=script_repo,
            command_repository=AsyncMock(),
            node_repository=node_repo,
            execution_repository=exec_repo,
            connector_factory=factory,
        )

        data = ScriptExecuteRequest(node_ids=[node1.id, node2.id], params={})
        result = await service.execute_script(orm_script.id, data)
        assert len(result.results) == 2


class TestResolveCommand:
    async def test_inline(self, service: ScriptService, cmd_repo: AsyncMock) -> None:
        step = ScriptStep(label="Step", type="inline", command="echo hello")
        result = await service._resolve_command(step, {})
        assert result == "echo hello"

    async def test_inline_with_global_params(self, service: ScriptService) -> None:
        step = ScriptStep(label="Step", type="inline", command="echo hello", params={})
        result = await service._resolve_command(step, {"unused": "value"})
        assert result == "echo hello"

    async def test_inline_no_command(self, service: ScriptService) -> None:
        step = ScriptStep(label="Step", type="inline")
        with pytest.raises(TemplateRenderError, match="no command"):
            await service._resolve_command(step, {})

    async def test_command_reference(
        self, service: ScriptService, cmd_repo: AsyncMock
    ) -> None:
        orm_cmd = make_orm_command(
            command="df -h {mount_point}",
            parameters=[{"name": "mount_point", "type": "string", "required": True}],
        )
        cmd_repo.get_by_id.return_value = orm_cmd
        step = ScriptStep(
            label="Step",
            type="command",
            command_id=orm_cmd.id,
            params={"mount_point": "/"},
        )
        result = await service._resolve_command(step, {})
        assert "df -h /" == result

    async def test_command_not_found(
        self, service: ScriptService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.get_by_id.return_value = None
        step = ScriptStep(label="Step", type="command", command_id=uuid.uuid4())
        with pytest.raises(CommandNotFoundError):
            await service._resolve_command(step, {})

    async def test_command_no_id(self, service: ScriptService) -> None:
        step = ScriptStep(label="Step", type="command")
        with pytest.raises(TemplateRenderError, match="no command_id"):
            await service._resolve_command(step, {})


class TestConnectorFactoryNotConfigured:
    def test_raises_runtime_error(self) -> None:
        from app.core.ssh_utils import get_connector_factory

        with pytest.raises(RuntimeError, match="ConnectorFactory not configured"):
            get_connector_factory(None)


class TestResolveCommandUnknownType:
    async def test_raises_on_unknown_type(self, service: ScriptService) -> None:
        from unittest.mock import MagicMock

        mock_step = MagicMock()
        mock_step.type = "unknown_type"
        with pytest.raises(TemplateRenderError, match="Unknown step type"):
            await service._resolve_command(mock_step, {})


class TestExecuteScriptCommandNotFound:
    async def test_step_fails_on_command_not_found(
        self,
        script_repo: AsyncMock,
        node_repo: AsyncMock,
        exec_repo: AsyncMock,
    ) -> None:
        from app.schemas.script import ScriptExecuteRequest

        cmd_repo = AsyncMock()
        cmd_repo.get_by_id.return_value = None

        orm_script = _make_orm_script(
            steps=[
                {
                    "label": "Step 1",
                    "type": "command",
                    "command_id": str(uuid.uuid4()),
                }
            ]
        )
        script_repo.get_by_id.return_value = orm_script

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        execution = _make_orm_execution(script_id=orm_script.id, node_id=orm_node.id)
        exec_repo.create.return_value = execution
        exec_repo.update.return_value = execution

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)

        factory = Mock()
        factory.create_ssh.return_value = connector

        svc = ScriptService(
            repository=script_repo,
            command_repository=cmd_repo,
            node_repository=node_repo,
            execution_repository=exec_repo,
            connector_factory=factory,
        )

        data = ScriptExecuteRequest(node_ids=[orm_node.id], params={})
        result = await svc.execute_script(orm_script.id, data)
        assert result.results[0].status == "failed"
        assert "not found" in result.results[0].steps[0].stderr.lower()


class TestLogWithAudit:
    async def test_calls_audit(self, script_repo: AsyncMock) -> None:
        audit_mock = AsyncMock()
        svc = ScriptService(
            repository=script_repo,
            command_repository=AsyncMock(),
            node_repository=AsyncMock(),
            execution_repository=AsyncMock(),
            audit_service=audit_mock,
        )
        await svc._log("test_action", node_id=uuid.uuid4(), details={"k": "v"})
        audit_mock.log.assert_awaited_once()
