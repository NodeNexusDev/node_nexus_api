"""Tests for transaction-safe script execution orchestration."""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.command_template import CommandTemplateDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.script_definition import ScriptDefinitionDTO
from app.application.dto.script_execution import ScriptExecutionRequestDTO
from app.core.exceptions import NodeNotFoundError, ScriptNotFoundError
from app.services.script_execution_service import ScriptExecutionService


def _node(node_id: uuid.UUID) -> NodeConnectionDTO:
    return NodeConnectionDTO(
        id=node_id,
        name="node",
        host="127.0.0.1",
        port=22,
        connection_type="ssh",
        username="root",
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
    node_reader.get_connection.return_value = _node(node_id)
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
    assert result.results[0].status == "completed"
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
            parameters=({"name": "service", "required": True},),
        )

    command_reader.get_template.side_effect = load_template
    node_reader = AsyncMock()
    node_reader.get_connection.return_value = _node(node_id)
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
    node_reader.get_connection.return_value = None
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
