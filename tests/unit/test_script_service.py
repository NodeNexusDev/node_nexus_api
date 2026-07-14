"""Unit tests for ScriptService."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ScriptNotFoundError
from app.repositories.command_repo import CommandRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository
from app.schemas.script import ScriptCreate, ScriptStep, ScriptUpdate
from app.services.script_service import ScriptService


def _make_orm_script(**overrides: Any) -> Any:
    from app.models.script import ScriptModel

    steps = [
        {"label": "Check disk", "type": "inline", "command": "df -h", "on_failure": "stop"}
    ]
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "deploy_check",
        "description": "Pre-deploy check",
        "steps": json.dumps(steps),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ScriptModel(**defaults)


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
    @pytest.mark.asyncio
    async def test_found(self, service: ScriptService, script_repo: AsyncMock) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script
        result = await service.get_script(orm_script.id)
        assert result.name == "deploy_check"
        assert len(result.steps) == 1

    @pytest.mark.asyncio
    async def test_not_found(self, service: ScriptService, script_repo: AsyncMock) -> None:
        script_repo.get_by_id.return_value = None
        with pytest.raises(ScriptNotFoundError):
            await service.get_script(uuid.uuid4())


class TestCreateScript:
    @pytest.mark.asyncio
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
    @pytest.mark.asyncio
    async def test_delete(self, service: ScriptService, script_repo: AsyncMock) -> None:
        orm_script = _make_orm_script()
        script_repo.get_by_id.return_value = orm_script
        script_repo.delete.return_value = True
        result = await service.delete_script(orm_script.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_not_found(self, service: ScriptService, script_repo: AsyncMock) -> None:
        script_repo.get_by_id.return_value = None
        with pytest.raises(ScriptNotFoundError):
            await service.delete_script(uuid.uuid4())
