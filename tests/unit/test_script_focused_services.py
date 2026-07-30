"""Tests for focused script management and history services."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.dto.script_execution import (
    ScriptExecutionPageDTO,
    ScriptExecutionQueryDTO,
)
from app.application.dto.script_management import (
    ScriptCreateDTO,
    ScriptPageDTO,
    ScriptStepDTO,
    ScriptUpdateDTO,
    ScriptViewDTO,
)
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.script_management_service import ScriptManagementService
from app.core.exceptions import ScriptNotFoundError


def _script_view() -> ScriptViewDTO:
    now = datetime.now(UTC)
    return ScriptViewDTO(
        id=uuid.uuid4(),
        name="deploy",
        description=None,
        steps=(ScriptStepDTO(label="check", type="inline", command="true"),),
        tags=("ops",),
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def management(gateway: AsyncMock) -> ScriptManagementService:
    return ScriptManagementService(reader=gateway, writer=gateway)


async def test_management_get_and_list_use_reader(
    management: ScriptManagementService, gateway: AsyncMock
) -> None:
    script = _script_view()
    gateway.get_script.return_value = script
    gateway.list_scripts.return_value = ScriptPageDTO(items=(script,), total=1)

    assert await management.get_script(script.id) == script
    scripts, total = await management.get_all_scripts(page=2, size=10, tags=["ops"])

    assert scripts == [script]
    assert total == 1
    query = gateway.list_scripts.await_args.args[0]
    assert (query.offset, query.limit, query.tags) == (10, 10, ("ops",))


async def test_management_create_update_delete_use_writer(
    management: ScriptManagementService, gateway: AsyncMock
) -> None:
    script = _script_view()
    create = ScriptCreateDTO(name=script.name, steps=script.steps)
    update = ScriptUpdateDTO(changes=(("description", None),))
    gateway.create_script.return_value = script
    gateway.update_script.return_value = script
    gateway.get_script.return_value = script

    assert await management.create_script(create) == script
    assert await management.update_script(script.id, update) == script
    assert await management.delete_script(script.id)
    gateway.create_script.assert_awaited_once_with(create)
    gateway.update_script.assert_awaited_once_with(script.id, update)
    gateway.delete_script.assert_awaited_once_with(script.id)


async def test_management_raises_when_script_is_missing(
    management: ScriptManagementService, gateway: AsyncMock
) -> None:
    gateway.get_script.return_value = None
    with pytest.raises(ScriptNotFoundError):
        await management.get_script(uuid.uuid4())


async def test_history_checks_script_and_builds_query(gateway: AsyncMock) -> None:
    script = _script_view()
    gateway.get_script.return_value = script
    gateway.list_executions.return_value = ScriptExecutionPageDTO(items=(), total=0)
    service = ScriptHistoryService(
        script_reader=gateway,
        execution_reader=gateway,
    )

    executions, total = await service.get_executions(script.id, page=3, size=5)

    assert executions == []
    assert total == 0
    gateway.list_executions.assert_awaited_once_with(
        ScriptExecutionQueryDTO(script_id=script.id, offset=10, limit=5)
    )


async def test_history_raises_before_query_when_script_is_missing(
    gateway: AsyncMock,
) -> None:
    gateway.get_script.return_value = None
    service = ScriptHistoryService(
        script_reader=gateway,
        execution_reader=gateway,
    )
    with pytest.raises(ScriptNotFoundError):
        await service.get_executions(uuid.uuid4())
    gateway.list_executions.assert_not_awaited()
