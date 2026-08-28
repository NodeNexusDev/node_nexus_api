"""Tests for transaction-safe script execution orchestration."""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.command_management import CommandParameterDTO
from app.application.dto.command_template import CommandTemplateDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.script_definition import ScriptDefinitionDTO
from app.application.dto.script_execution import ScriptExecutionRequestDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.script_execution_service import ScriptExecutionService
from app.core.exceptions import NodeNotFoundError, ScriptNotFoundError
from app.core.types import JsonObject


def _node(node_id: uuid.UUID) -> NodeConnectionDTO:
    return NodeConnectionDTO(
        id=node_id,
        name="node",
        endpoint=NodeEndpoint(host="127.0.0.1", port=22, connection_type="ssh"),
        credentials=NodeCredentials(username="root"),
    )


def _service(
    script_reader: AsyncMock,
    command_reader: AsyncMock,
    node_reader: AsyncMock,
    writer: AsyncMock,
    factory: Mock,
) -> ScriptExecutionService:
    return ScriptExecutionService(
        script_reader=script_reader,
        command_reader=command_reader,
        node_reader=node_reader,
        execution_writer=writer,
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=factory,
    )


async def test_remote_worker_runs_between_short_writer_calls() -> None:
    events: list[str] = []
    script_id = uuid.uuid4()
    node_id = uuid.uuid4()
    script_reader = AsyncMock()
    script_reader.get_definition.return_value = ScriptDefinitionDTO(
        id=script_id,
        steps=(
            {
                "label": "check",
                "type": "inline",
                "command": "echo ok",
                "on_failure": "stop",
            },
        ),
    )
    command_reader = AsyncMock()
    node_reader = AsyncMock()
    node_reader.get_connections_by_ids.return_value = [_node(node_id)]
    writer = AsyncMock()
    writer.create_execution.side_effect = lambda data: (
        events.append("create"),
        uuid.uuid4(),
    )[1]
    writer.update_execution.side_effect = lambda execution_id, data: events.append(
        "update"
    )
    connector = AsyncMock()
    connector.__aenter__.side_effect = lambda: (
        events.append("remote"),
        connector,
    )[1]
    connector.execute_command.return_value = ("ok", "", 0)
    factory = Mock()
    factory.create_ssh.return_value = connector

    result = await _service(
        script_reader, command_reader, node_reader, writer, factory
    ).execute_script(
        script_id,
        ScriptExecutionRequestDTO(node_ids=(node_id,)),
    )

    assert events == ["create", "remote", "update"]
    assert result.results[0].status == "success"
    assert result.results[0].steps[0].stdout == "ok"


async def test_command_templates_are_loaded_before_remote_execution() -> None:
    events: list[str] = []
    command_id = uuid.uuid4()
    script_id = uuid.uuid4()
    node_id = uuid.uuid4()
    script_reader = AsyncMock()
    script_reader.get_definition.return_value = ScriptDefinitionDTO(
        id=script_id,
        steps=(
            {
                "label": "restart",
                "type": "command",
                "command_id": str(command_id),
                "params": {"service": "nginx"},
            },
        ),
    )
    command_reader = AsyncMock()

    async def load_template(_: uuid.UUID) -> CommandTemplateDTO:
        events.append("command_read")
        return CommandTemplateDTO(
            id=command_id,
            command="systemctl restart {service}",
            parameters=(CommandParameterDTO(name="service", required=True),),
        )

    command_reader.get_template.side_effect = load_template
    node_reader = AsyncMock()
    node_reader.get_connections_by_ids.return_value = [_node(node_id)]
    writer = AsyncMock()
    writer.create_execution.return_value = uuid.uuid4()
    connector = AsyncMock()
    connector.__aenter__.side_effect = lambda: (
        events.append("remote"),
        connector,
    )[1]
    connector.execute_command.return_value = ("", "", 0)
    factory = Mock()
    factory.create_ssh.return_value = connector

    await _service(
        script_reader, command_reader, node_reader, writer, factory
    ).execute_script(
        script_id,
        ScriptExecutionRequestDTO(node_ids=(node_id,)),
    )

    assert events == ["command_read", "remote"]
    connector.execute_command.assert_awaited_once_with("systemctl restart nginx")


async def test_missing_script_stops_before_loading_nodes() -> None:
    script_reader = AsyncMock()
    script_reader.get_definition.return_value = None
    node_reader = AsyncMock()
    service = _service(
        script_reader,
        AsyncMock(),
        node_reader,
        AsyncMock(),
        Mock(),
    )
    with pytest.raises(ScriptNotFoundError):
        await service.execute_script(
            uuid.uuid4(),
            ScriptExecutionRequestDTO(node_ids=(uuid.uuid4(),)),
        )
    node_reader.get_connection.assert_not_awaited()


async def test_missing_node_stops_before_creating_execution() -> None:
    script_id = uuid.uuid4()
    script_reader = AsyncMock()
    script_reader.get_definition.return_value = ScriptDefinitionDTO(
        id=script_id,
        steps=({"label": "check", "type": "inline", "command": "true"},),
    )
    node_reader = AsyncMock()
    node_reader.get_connections_by_ids.return_value = []
    writer = AsyncMock()
    service = _service(
        script_reader,
        AsyncMock(),
        node_reader,
        writer,
        Mock(),
    )
    with pytest.raises(NodeNotFoundError):
        await service.execute_script(
            script_id,
            ScriptExecutionRequestDTO(node_ids=(uuid.uuid4(),)),
        )
    writer.create_execution.assert_not_awaited()


# ---------------------------------------------------------------------------
# Step resolution error paths
# ---------------------------------------------------------------------------


def _make_service_for_resolve(
    command_reader: AsyncMock | None = None,
    audit: AsyncMock | None = None,
    connector: AsyncMock | None = None,
) -> ScriptExecutionService:
    """Build a ScriptExecutionService wired for _resolve_step / _run_remote tests."""
    script_reader = AsyncMock()
    node_id = uuid.uuid4()
    script_id = uuid.uuid4()
    script_reader.get_definition.return_value = ScriptDefinitionDTO(
        id=script_id,
        steps=({"label": "s1", "type": "inline", "command": "true"},),
    )
    node_reader = AsyncMock()
    node_reader.get_connections_by_ids.return_value = [_node(node_id)]
    writer = AsyncMock()
    factory = Mock()
    if connector is None:
        connector = AsyncMock()
        connector.execute_command.return_value = ("", "", 0)
    factory.create_ssh.return_value = connector
    from app.adapters.security import AesGcmCredentialCipher

    return ScriptExecutionService(
        script_reader=script_reader,
        command_reader=command_reader or AsyncMock(),
        node_reader=node_reader,
        execution_writer=writer,
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=factory,
        audit_service=audit,
    )


@pytest.mark.asyncio
async def test_resolve_inline_step_without_command_returns_error() -> None:
    """Inline step missing the 'command' key produces a resolution_error."""
    service = _make_service_for_resolve()
    raw_step: JsonObject = {"label": "bad", "type": "inline"}
    result = await service._resolve_step(raw_step, {})
    assert result.resolution_error is not None
    assert "no command" in result.resolution_error.lower()


@pytest.mark.asyncio
async def test_resolve_command_step_without_id_returns_error() -> None:
    """Command step missing 'command_id' produces a resolution_error."""
    service = _make_service_for_resolve()
    raw_step: JsonObject = {"label": "bad", "type": "command"}
    result = await service._resolve_step(raw_step, {})
    assert result.resolution_error is not None
    assert "no command_id" in result.resolution_error.lower()


@pytest.mark.asyncio
async def test_resolve_command_step_template_not_found() -> None:
    """Command step with valid id but missing template produces a resolution_error."""
    command_reader = AsyncMock()
    command_reader.get_template.return_value = None
    service = _make_service_for_resolve(command_reader=command_reader)
    raw_step: JsonObject = {
        "label": "bad",
        "type": "command",
        "command_id": str(uuid.uuid4()),
    }
    result = await service._resolve_step(raw_step, {})
    assert result.resolution_error is not None
    assert "not found" in result.resolution_error.lower()


@pytest.mark.asyncio
async def test_resolve_unknown_step_type_returns_error() -> None:
    """Unknown step type produces a resolution_error."""
    service = _make_service_for_resolve()
    raw_step: JsonObject = {"label": "bad", "type": "unknown"}
    result = await service._resolve_step(raw_step, {})
    assert result.resolution_error is not None
    assert "unknown step type" in result.resolution_error.lower()


@pytest.mark.asyncio
async def test_run_remote_with_resolution_error_records_stderr() -> None:
    """_run_remote places resolution_error into the stderr slot."""
    from app.application.dto.script_execution import (
        ResolvedScriptStepDTO,
        ScriptExecutionTargetDTO,
    )

    service = _make_service_for_resolve()
    node_id = uuid.uuid4()
    target = ScriptExecutionTargetDTO(
        execution_id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        node=_node(node_id),
        steps=(
            ResolvedScriptStepDTO(
                label="bad",
                command="",
                on_failure="stop",
                resolution_error="boom",
            ),
        ),
    )
    result = await service._run_remote(target)
    assert result.status == "error"
    assert result.steps[0].stderr == "boom"
    assert result.steps[0].exit_code == 1


@pytest.mark.asyncio
async def test_run_remote_continue_keeps_running_but_marks_result_as_error() -> None:
    """A failed continue step must not turn the overall result into success."""
    connector = AsyncMock()
    connector.execute_command.side_effect = [
        ("", "first failed", 1),
        ("second ran", "", 0),
    ]
    service = _make_service_for_resolve(connector=connector)
    from app.application.dto.script_execution import (
        ResolvedScriptStepDTO,
        ScriptExecutionTargetDTO,
    )

    target = ScriptExecutionTargetDTO(
        execution_id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        node=_node(uuid.uuid4()),
        steps=(
            ResolvedScriptStepDTO(
                label="first",
                command="false",
                on_failure="continue",
            ),
            ResolvedScriptStepDTO(
                label="second",
                command="echo second",
                on_failure="stop",
            ),
        ),
    )

    result = await service._run_remote(target)

    assert result.status == "error"
    assert [step.exit_code for step in result.steps] == [1, 0]
    assert connector.execute_command.await_count == 2


@pytest.mark.asyncio
async def test_run_remote_connector_exception_marks_failed() -> None:
    """_run_remote catches connector exceptions and marks status as failed."""
    connector = AsyncMock()
    connector.execute_command.side_effect = RuntimeError("ssh down")
    service = _make_service_for_resolve(connector=connector)
    from app.application.dto.script_execution import ScriptExecutionTargetDTO

    node_id = uuid.uuid4()
    from app.application.dto.script_execution import ResolvedScriptStepDTO

    target = ScriptExecutionTargetDTO(
        execution_id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        node=_node(node_id),
        steps=(ResolvedScriptStepDTO(label="ok", command="true", on_failure="stop"),),
    )
    result = await service._run_remote(target)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_log_result_writes_to_audit_when_set() -> None:
    """_log_result calls audit_service when it is provided."""
    audit = AsyncMock()
    service = _make_service_for_resolve(audit=audit)
    from app.application.dto.script_execution import ScriptNodeResultDTO

    script_id = uuid.uuid4()
    node_id = uuid.uuid4()
    result = ScriptNodeResultDTO(
        execution_id=uuid.uuid4(),
        node_id=node_id,
        node_name="node",
        status="success",
        steps=(),
    )
    await service._log_result(script_id, result)
    audit.log.assert_awaited_once()
    args = audit.log.call_args
    action = args.kwargs.get("action") or (args.args[0] if args.args else None)
    assert action == "execute"
    node = args.kwargs.get("node_id") or (args.args[1] if len(args.args) > 1 else None)
    assert node == node_id
