"""Unit tests for CommandService."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandExecuteRequestDTO,
    CommandPageDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.application.dto.command_template import CommandTemplateDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
)
from app.services.command_service import CommandService


def make_command_view(**overrides: object) -> CommandViewDTO:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "name": "check_disk",
        "description": None,
        "command": "df -h",
        "parameters": (),
        "tags": (),
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return CommandViewDTO(**values)  # type: ignore[arg-type]


@pytest.fixture
def command_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_reader() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def connector_factory() -> Mock:
    return Mock()


@pytest.fixture
def service(
    command_gateway: AsyncMock,
    node_reader: AsyncMock,
    connector_factory: Mock,
) -> CommandService:
    return CommandService(
        reader=command_gateway,
        writer=command_gateway,
        command_reader=command_gateway,
        node_reader=node_reader,
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=connector_factory,
    )


class TestManagement:
    async def test_get_found(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        command = make_command_view()
        command_gateway.get_command.return_value = command
        assert await service.get_command(command.id) == command

    async def test_get_not_found(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        command_gateway.get_command.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.get_command(uuid.uuid4())

    async def test_list_builds_query(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        command = make_command_view()
        command_gateway.list_commands.return_value = CommandPageDTO(
            items=(command,), total=1
        )
        commands, total = await service.get_all_commands(page=2, size=10, tags=["ops"])
        assert commands == [command]
        assert total == 1
        query = command_gateway.list_commands.await_args.args[0]
        assert (query.offset, query.limit, query.tags) == (10, 10, ("ops",))

    async def test_create_delegates_dto(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        data = CommandCreateDTO(name="check_disk", command="df -h")
        command_gateway.create_command.return_value = make_command_view()
        result = await service.create_command(data)
        assert result.name == "check_disk"
        command_gateway.create_command.assert_awaited_once_with(data)

    async def test_update_delegates_dto(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        command = make_command_view()
        data = CommandUpdateDTO(changes=(("name", "new-name"),))
        command_gateway.update_command.return_value = command
        assert await service.update_command(command.id, data) == command
        command_gateway.update_command.assert_awaited_once_with(command.id, data)

    async def test_update_not_found(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        command_gateway.update_command.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.update_command(
                uuid.uuid4(), CommandUpdateDTO(changes=(("name", "x"),))
            )

    async def test_delete(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        command = make_command_view()
        command_gateway.get_command.return_value = command
        assert await service.delete_command(command.id)
        command_gateway.delete_command.assert_awaited_once_with(command.id)


class TestExecuteCommand:
    async def test_success(
        self,
        service: CommandService,
        command_gateway: AsyncMock,
        node_reader: AsyncMock,
        connector_factory: Mock,
    ) -> None:
        command_id = uuid.uuid4()
        node_id = uuid.uuid4()
        command_gateway.get_template.return_value = CommandTemplateDTO(
            id=command_id,
            command="systemctl restart {service}",
            parameters=({"name": "service", "type": "string", "required": True},),
        )
        node_reader.get_connection.return_value = NodeConnectionDTO(
            id=node_id,
            name="node",
            host="127.0.0.1",
            port=22,
            connection_type="ssh",
            username="root",
        )
        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)
        connector_factory.create_ssh.return_value = connector

        result = await service.execute_command(
            command_id,
            CommandExecuteRequestDTO(node_id=node_id, params=(("service", "nginx"),)),
        )

        assert result.exit_code == 0
        connector.execute_command.assert_awaited_once_with("systemctl restart nginx")

    async def test_command_not_found(
        self, service: CommandService, command_gateway: AsyncMock
    ) -> None:
        command_gateway.get_template.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.execute_command(
                uuid.uuid4(), CommandExecuteRequestDTO(node_id=uuid.uuid4())
            )

    async def test_node_not_found(
        self,
        service: CommandService,
        command_gateway: AsyncMock,
        node_reader: AsyncMock,
    ) -> None:
        command_id = uuid.uuid4()
        command_gateway.get_template.return_value = CommandTemplateDTO(
            id=command_id, command="true", parameters=()
        )
        node_reader.get_connection.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.execute_command(
                command_id, CommandExecuteRequestDTO(node_id=uuid.uuid4())
            )

    async def test_connector_error(
        self,
        service: CommandService,
        command_gateway: AsyncMock,
        node_reader: AsyncMock,
        connector_factory: Mock,
    ) -> None:
        command_id = uuid.uuid4()
        node_id = uuid.uuid4()
        command_gateway.get_template.return_value = CommandTemplateDTO(
            id=command_id, command="true", parameters=()
        )
        node_reader.get_connection.return_value = NodeConnectionDTO(
            id=node_id,
            name="node",
            host="127.0.0.1",
            port=22,
            connection_type="ssh",
            username="root",
        )
        connector = AsyncMock()
        connector.__aenter__.side_effect = RuntimeError("SSH error")
        connector_factory.create_ssh.return_value = connector
        with pytest.raises(ConnectionFailedError):
            await service.execute_command(
                command_id, CommandExecuteRequestDTO(node_id=node_id)
            )


class TestLogWithAudit:
    async def test_calls_audit(
        self,
        command_gateway: AsyncMock,
        node_reader: AsyncMock,
        connector_factory: Mock,
    ) -> None:
        audit = AsyncMock()
        service = CommandService(
            reader=command_gateway,
            writer=command_gateway,
            command_reader=command_gateway,
            node_reader=node_reader,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=connector_factory,
            audit_service=audit,
        )
        await service._log("test_action", node_id=uuid.uuid4(), details={"k": "v"})
        audit.log.assert_awaited_once()
