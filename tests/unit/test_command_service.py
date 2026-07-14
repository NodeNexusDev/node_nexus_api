"""Unit tests for CommandService."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
)
from app.repositories.command_repo import CommandRepository
from app.repositories.node_repo import NodeRepository
from app.schemas.command import CommandCreate, CommandExecuteRequest, CommandUpdate
from app.services.command_service import CommandService


def _make_orm_command(**overrides: Any) -> Any:
    from app.models.command import CommandModel

    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "check_disk",
        "description": "Check disk usage",
        "command": "df -h",
        "parameters": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return CommandModel(**defaults)


def _make_orm_node(**overrides: Any) -> Any:
    from app.models.node import NodeModel

    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "server-1",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "password": None,
        "ssh_key": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


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
    @pytest.mark.asyncio
    async def test_found(self, service: CommandService, cmd_repo: AsyncMock) -> None:
        orm_cmd = _make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd
        result = await service.get_command(orm_cmd.id)
        assert result.name == "check_disk"

    @pytest.mark.asyncio
    async def test_not_found(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.get_by_id.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.get_command(uuid.uuid4())


class TestCreateCommand:
    @pytest.mark.asyncio
    async def test_create(self, service: CommandService, cmd_repo: AsyncMock) -> None:
        orm_cmd = _make_orm_command()
        cmd_repo.create.return_value = orm_cmd
        data = CommandCreate(name="check_disk", command="df -h")
        result = await service.create_command(data)
        assert result.name == "check_disk"
        cmd_repo.create.assert_called_once()


class TestDeleteCommand:
    @pytest.mark.asyncio
    async def test_delete(self, service: CommandService, cmd_repo: AsyncMock) -> None:
        orm_cmd = _make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd
        cmd_repo.delete.return_value = True
        result = await service.delete_command(orm_cmd.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_not_found(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.get_by_id.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.delete_command(uuid.uuid4())


class TestGetAllCommands:
    @pytest.mark.asyncio
    async def test_returns_list(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        orm_cmds = [_make_orm_command(), _make_orm_command()]
        cmd_repo.get_all.return_value = orm_cmds
        cmd_repo.count.return_value = 2
        commands, total = await service.get_all_commands()
        assert len(commands) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_empty_list(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.get_all.return_value = []
        cmd_repo.count.return_value = 0
        commands, total = await service.get_all_commands()
        assert commands == []
        assert total == 0


class TestUpdateCommand:
    @pytest.mark.asyncio
    async def test_update_name(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        orm_cmd = _make_orm_command()
        cmd_repo.update.return_value = orm_cmd
        data = CommandUpdate(name="new-name")
        result = await service.update_command(orm_cmd.id, data)
        assert result.name == "check_disk"

    @pytest.mark.asyncio
    async def test_update_with_parameters(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        params = [{"name": "mount_point", "type": "string", "required": True}]
        orm_cmd = _make_orm_command(parameters=json.dumps(params))
        cmd_repo.update.return_value = orm_cmd
        data = CommandUpdate(parameters=params)
        result = await service.update_command(orm_cmd.id, data)
        assert result.parameters is not None

    @pytest.mark.asyncio
    async def test_not_found(
        self, service: CommandService, cmd_repo: AsyncMock
    ) -> None:
        cmd_repo.update.return_value = None
        data = CommandUpdate(name="x")
        with pytest.raises(CommandNotFoundError):
            await service.update_command(uuid.uuid4(), data)


class TestExecuteCommand:
    @pytest.mark.asyncio
    async def test_success(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        orm_cmd = _make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd

        orm_node = _make_orm_node()
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_node_not_found(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        orm_cmd = _make_orm_command()
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

    @pytest.mark.asyncio
    async def test_connector_error(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        orm_cmd = _make_orm_command()
        cmd_repo.get_by_id.return_value = orm_cmd

        orm_node = _make_orm_node()
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

    @pytest.mark.asyncio
    async def test_with_params(
        self,
        cmd_repo: AsyncMock,
        node_repo: AsyncMock,
    ) -> None:
        params = [{"name": "service", "type": "string", "required": True}]
        orm_cmd = _make_orm_command(
            command="systemctl restart {service}",
            parameters=json.dumps(params),
        )
        cmd_repo.get_by_id.return_value = orm_cmd

        orm_node = _make_orm_node()
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
        service = CommandService(
            repository=AsyncMock(),
            node_repository=AsyncMock(),
            connector_factory=None,
        )
        with pytest.raises(RuntimeError, match="ConnectorFactory not configured"):
            service._get_connector_factory()
