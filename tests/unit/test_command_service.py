"""Unit tests for CommandService."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import CommandNotFoundError, NodeNotFoundError
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
    async def test_not_found(self, service: CommandService, cmd_repo: AsyncMock) -> None:
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
    async def test_not_found(self, service: CommandService, cmd_repo: AsyncMock) -> None:
        cmd_repo.get_by_id.return_value = None
        with pytest.raises(CommandNotFoundError):
            await service.delete_command(uuid.uuid4())
