"""Tests for the SQLAlchemy script gateway."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.persistence.script_gateway import SqlAlchemyScriptGateway
from app.application.dto.script_execution import ScriptExecutionQueryDTO
from app.application.dto.script_management import (
    ScriptCreateDTO,
    ScriptListQueryDTO,
    ScriptStepDTO,
    ScriptUpdateDTO,
)
from app.models.script import ScriptModel
from app.models.script_execution import ScriptExecutionModel


def _sessionmaker() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    factory = MagicMock()
    factory.return_value = context
    factory.begin.return_value = context
    return factory, session


def _script(**overrides: object) -> ScriptModel:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "name": "deploy",
        "description": None,
        "steps": [
            {
                "label": "check",
                "type": "inline",
                "command": "true",
                "params": {},
                "on_failure": "stop",
            }
        ],
        "tags": ["ops"],
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return ScriptModel(**values)


async def test_get_script_maps_orm_to_view() -> None:
    factory, _ = _sessionmaker()
    script = _script()
    with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_type:
        repo_type.return_value.get_by_id = AsyncMock(return_value=script)
        result = await SqlAlchemyScriptGateway(factory).get_script(script.id)

    assert result is not None
    assert result.steps[0].command == "true"
    assert result.tags == ("ops",)


async def test_list_scripts_maps_query_and_page() -> None:
    factory, _ = _sessionmaker()
    script = _script()
    with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_type:
        repository = repo_type.return_value
        repository.get_all = AsyncMock(return_value=[script])
        repository.count = AsyncMock(return_value=1)
        result = await SqlAlchemyScriptGateway(factory).list_scripts(
            ScriptListQueryDTO(offset=10, limit=5, tags=("ops",))
        )

    assert result.total == 1
    repository.get_all.assert_awaited_once_with(
        skip=10, limit=5, tags=["ops"], search=None
    )
    repository.count.assert_awaited_once_with(tags=["ops"], search=None)


async def test_list_scripts_with_search() -> None:
    factory, _ = _sessionmaker()
    script = _script()
    with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_type:
        repository = repo_type.return_value
        repository.get_all = AsyncMock(return_value=[script])
        repository.count = AsyncMock(return_value=1)
        result = await SqlAlchemyScriptGateway(factory).list_scripts(
            ScriptListQueryDTO(offset=0, limit=10, search="deploy")
        )

    assert result.total == 1
    repository.get_all.assert_awaited_once_with(
        skip=0, limit=10, tags=None, search="deploy"
    )
    repository.count.assert_awaited_once_with(tags=None, search="deploy")


async def test_list_tags_delegates_to_repository() -> None:
    factory, _ = _sessionmaker()
    with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_type:
        repository = repo_type.return_value
        repository.get_all_tags = AsyncMock(return_value=["ops", "prod"])
        result = await SqlAlchemyScriptGateway(factory).list_tags()

    assert result == ["ops", "prod"]
    repository.get_all_tags.assert_awaited_once_with()


async def test_create_script_normalizes_steps_and_tags() -> None:
    factory, _ = _sessionmaker()
    script = _script()
    data = ScriptCreateDTO(
        name="deploy",
        steps=(
            ScriptStepDTO(
                label="run",
                type="command",
                command_id=uuid.uuid4(),
                params=(("environment", "prod"),),
            ),
        ),
        tags=("ops",),
    )
    with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_type:
        repository = repo_type.return_value
        repository.create = AsyncMock(return_value=script)
        await SqlAlchemyScriptGateway(factory).create_script(data)

    assert repository.create.await_args is not None
    persisted = repository.create.await_args.args[0]
    assert persisted["steps"][0]["command_id"] == str(data.steps[0].command_id)
    assert persisted["steps"][0]["params"] == {"environment": "prod"}
    assert persisted["tags"] == ["ops"]
    factory.begin.assert_called_once_with()


async def test_update_script_normalizes_immutable_values() -> None:
    factory, _ = _sessionmaker()
    script = _script()
    script_id = uuid.uuid4()
    data = ScriptUpdateDTO(
        changes=(
            ("steps", (ScriptStepDTO(label="run", type="inline", command="true"),)),
            ("tags", ("ops",)),
        )
    )
    with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_type:
        repository = repo_type.return_value
        repository.update = AsyncMock(return_value=script)
        await SqlAlchemyScriptGateway(factory).update_script(script_id, data)

    assert repository.update.await_args is not None
    persisted = repository.update.await_args.args[1]
    assert persisted["steps"][0]["label"] == "run"
    assert persisted["tags"] == ["ops"]


async def test_delete_script_uses_adapter_owned_transaction() -> None:
    factory, session = _sessionmaker()
    script = _script()
    with patch("app.adapters.persistence.script_gateway.ScriptRepository") as repo_type:
        repo_type.return_value.get_by_id = AsyncMock(return_value=script)
        deleted = await SqlAlchemyScriptGateway(factory).delete_script(script.id)

    assert deleted is True
    session.delete.assert_awaited_once_with(script)
    session.flush.assert_awaited_once_with()


async def test_list_executions_maps_history_page() -> None:
    factory, _ = _sessionmaker()
    now = datetime.now(UTC)
    execution = ScriptExecutionModel(
        id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        params={"environment": "prod"},
        status="success",
        steps=[
            {
                "step_index": 0,
                "label": "run",
                "command_fingerprint": "abc",
                "stdout": "ok",
                "stderr": "",
                "stdout_bytes": 2,
                "stderr_bytes": 0,
                "truncated": False,
                "exit_code": 0,
            }
        ],
        started_at=now,
        finished_at=now,
    )
    with patch(
        "app.adapters.persistence.script_gateway.ScriptExecutionRepository"
    ) as repo_type:
        repository = repo_type.return_value
        repository.get_by_script_id = AsyncMock(return_value=[execution])
        repository.count_by_script_id = AsyncMock(return_value=1)
        result = await SqlAlchemyScriptGateway(factory).list_executions(
            ScriptExecutionQueryDTO(script_id=execution.script_id, offset=20, limit=10)
        )

    assert result.total == 1
    assert result.items[0].status == "success"
    assert result.items[0].steps[0].stdout == "ok"
    repository.get_by_script_id.assert_awaited_once_with(
        execution.script_id, skip=20, limit=10, trigger=None
    )


def test_execution_mapping_rejects_legacy_terminal_statuses() -> None:
    now = datetime.now(UTC)
    execution = ScriptExecutionModel(
        id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        status="completed",
        started_at=now,
    )

    with pytest.raises(ValueError, match="Stored script execution status is invalid"):
        SqlAlchemyScriptGateway._to_execution(execution)
