"""Unit tests for CommandService."""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.application.dto.command_template import CommandTemplateDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
)
from app.repositories.command_repo import CommandRepository
from app.repositories.node_repo import NodeRepository
from app.schemas.command import CommandCreate, CommandExecuteRequest, CommandUpdate
from app.services.command_service import CommandService
from tests.unit.conftest import make_orm_command, make_orm_node


@pytest.fixture
def cmd_repo() -> AsyncMock:
    return AsyncMock(spec=CommandRepository)


@pytest.fixture
def node_repo() -> AsyncMock:
    return AsyncMock(spec=NodeRepository)


@pytest.fixture
def service(cmd_repo: AsyncMock, node_repo: AsyncMock) -> CommandService:
    return CommandService(repository=cmd_repo, node_repository=node_repo)


class TestGetCommand:
    async def test_found(self, service: CommandService, cmd_repo: AsyncMock) -> None:
        orm_cmd = make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd
        result = await service.get_command(orm_cmd.id)
        assert result.name == "check_disk"

    async def test_not_found(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.get_by_id.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.get_command(uuid.uuid4())


class TestCreateCommand:
    async def test_create(self, service: CommandService, cmd_repo: AsyncMock) -> None:
        orm_cmd = make_orm_command()
        cmd_repo.create.return_value = orm_cmd
        data = CommandCreate(name="check_disk", command="df -h")
        result = await service.create_command(data)
        assert result.name == "check_disk"
        cmd_repo.create.assert_called_once()


class TestDeleteCommand:
    async def test_delete(self, service: CommandService, cmd_repo: AsyncMock) -> None:
        orm_cmd = make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd
        cmd_repo.delete.return_value = True
        result = await service.delete_command(orm_cmd.id)
        assert result is True

    async def test_not_found(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.get_by_id.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.delete_command(uuid.uuid4())


class TestGetAllCommands:
    async def test_returns_list(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        orm_cmds = [make_orm_command(), make_orm_command()]
        cmd_repo.get_all.return_value = orm_cmds
        cmd_repo.count.return_value = 2
        commands, total = await service.get_all_commands()
        assert len(commands) == 2
        assert total == 2

    async def test_empty_list(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.get_all.return_value = []
        cmd_repo.count.return_value = 0
        commands, total = await service.get_all_commands()
        assert commands == []
        assert total == 0


class TestUpdateCommand:
    async def test_update_name(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        orm_cmd = make_orm_command()
        cmd_repo.update.return_value = orm_cmd
        data = CommandUpdate(name="new-name")
        result = await service.update_command(orm_cmd.id, data)
        assert result.name == "check_disk"

    async def test_update_with_parameters(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        params = [{"name": "mount_point", "type": "string", "required": True}]
        orm_cmd = make_orm_command(parameters=params)
        cmd_repo.update.return_value = orm_cmd
        data = CommandUpdate(parameters=params)
        result = await service.update_command(orm_cmd.id, data)
        assert result.parameters is not None

    async def test_not_found(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.update.return_value = None
        data = CommandUpdate(name="x")
        with pytest.raises(CommandNotFoundError):
            await service.update_command(uuid.uuid4(), data)


class TestExecuteCommand:
    async def test_uses_application_readers_for_remote_execution(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        command_id = uuid.uuid4()
        node_id = uuid.uuid4()
        command_reader = AsyncMock()
        command_reader.get_template.return_value = CommandTemplateDTO(
            id=command_id,
            command="echo ok",
            parameters=(),
        )
        node_reader = AsyncMock()
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
        factory = Mock()
        factory.create_ssh.return_value = connector
        service = CommandService(
            repository=cmd_repo,
            node_repository=node_repo,
            connector_factory=factory,
            command_reader=command_reader,
            node_reader=node_reader,
        )

        result = await service.execute_command(
            command_id,
            CommandExecuteRequest(node_id=node_id, params={}),
        )

        assert result.exit_code == 0
        cmd_repo.get_by_id.assert_not_awaited()
        node_repo.get_by_id.assert_not_awaited()

    async def test_success(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        orm_cmd = make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)

        factory = Mock()
        factory.create_ssh.return_value = connector

        service = CommandService(
            repository=cmd_repo,
            node_repository=node_repo,
            connector_factory=factory,
        )

        data = CommandExecuteRequest(node_id=orm_node.id, params={})
        result = await service.execute_command(orm_cmd.id, data)
        assert result.stdout == "ok"
        assert result.exit_code == 0

    async def test_command_not_found(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        cmd_repo.get_by_id.return_value = None
        service = CommandService(
            repository=cmd_repo,
            node_repository=node_repo,
            connector_factory=Mock(),
        )
        data = CommandExecuteRequest(node_id=uuid.uuid4(), params={})
        with pytest.raises(CommandNotFoundError):
            await service.execute_command(uuid.uuid4(), data)

    async def test_node_not_found(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        orm_cmd = make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd
        node_repo.get_by_id.return_value = None

        service = CommandService(
            repository=cmd_repo,
            node_repository=node_repo,
            connector_factory=Mock(),
        )

        data = CommandExecuteRequest(node_id=uuid.uuid4(), params={})
        with pytest.raises(NodeNotFoundError):
            await service.execute_command(orm_cmd.id, data)

    async def test_connector_error(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        orm_cmd = make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        connector = AsyncMock()
        connector.connect = AsyncMock(side_effect=Exception("SSH error"))

        factory = Mock()
        factory.create_ssh.return_value = connector

        service = CommandService(
            repository=cmd_repo,
            node_repository=node_repo,
            connector_factory=factory,
        )

        data = CommandExecuteRequest(node_id=orm_node.id, params={})
        with pytest.raises(ConnectionFailedError):
            await service.execute_command(orm_cmd.id, data)

    async def test_with_params(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        params = [{"name": "service", "type": "string", "required": True}]
        orm_cmd = make_orm_command(
            command="systemctl restart {service}",
            parameters=params,
        )
        cmd_repo.get_by_id.return_value = orm_cmd

        orm_node = make_orm_node()
        node_repo.get_by_id.return_value = orm_node

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)

        factory = Mock()
        factory.create_ssh.return_value = connector

        service = CommandService(
            repository=cmd_repo,
            node_repository=node_repo,
            connector_factory=factory,
        )

        data = CommandExecuteRequest(node_id=orm_node.id, params={"service": "nginx"})
        result = await service.execute_command(orm_cmd.id, data)
        assert result.exit_code == 0
        connector.execute_command.assert_called_once_with("systemctl restart nginx")


class TestConnectorFactoryNotConfigured:
    def test_raises_runtime_error(self) -> None:
        from app.core.ssh_utils import get_connector_factory

        with pytest.raises(RuntimeError, match="ConnectorFactory not configured"):
            get_connector_factory(None)


class TestLogWithAudit:
    async def test_calls_audit(self) -> None:
        from unittest.mock import AsyncMock

        from app.repositories.command_repo import CommandRepository
        from app.services.command_service import CommandService

        audit_mock = AsyncMock()
        repo = AsyncMock(spec=CommandRepository)
        svc = CommandService(
            repository=repo,
            node_repository=AsyncMock(),
            audit_service=audit_mock,
        )
        await svc._log("test_action", node_id=uuid.uuid4(), details={"k": "v"})
        audit_mock.log.assert_awaited_once()
