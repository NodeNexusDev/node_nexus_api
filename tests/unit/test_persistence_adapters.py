"""Tests for short-scope persistence adapters."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
from app.adapters.persistence.script_gateway import (
    ScopedScriptDefinitionReader,
    ScopedScriptExecutionWriter,
)
from tests.helpers import TransactionSpy


def context_factory(session: object, *, begin: bool = False) -> MagicMock:
    context = AsyncMock()
    context.__aenter__.return_value = session
    factory = MagicMock()
    if begin:
        factory.begin.return_value = context
    else:
        factory.return_value = context
    return factory


async def test_command_reader_found_and_missing() -> None:
    repository = MagicMock()
    repository.get_by_id = AsyncMock(
        side_effect=[
            SimpleNamespace(id=uuid4(), command="echo ok", parameters=["name"]),
            None,
        ]
    )
    with patch(
        "app.adapters.persistence.command_reader.CommandRepository",
        return_value=repository,
    ):
        reader = ScopedCommandTemplateReader(context_factory(object()))
        found = await reader.get_template(uuid4())
        missing = await reader.get_template(uuid4())
    assert found is not None
    assert found.command == "echo ok"
    assert found.parameters == ("name",)
    assert missing is None


async def test_command_reader_closes_session_before_returning() -> None:
    repository = MagicMock()
    repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(id=uuid4(), command="echo ok", parameters=[])
    )
    boundary = TransactionSpy()
    with patch(
        "app.adapters.persistence.command_reader.CommandRepository",
        return_value=repository,
    ):
        result = await ScopedCommandTemplateReader(boundary).get_template(uuid4())

    assert result is not None
    assert boundary.session_entries == 1
    assert boundary.session_exits == 1
    assert boundary.session_active is False


async def test_node_reader_delegates_all_queries() -> None:
    repository = MagicMock()
    expected = [object()]
    repository.get_connection = AsyncMock(return_value=object())
    repository.get_connections_by_ids = AsyncMock(return_value=expected)
    repository.get_connections_by_tags = AsyncMock(return_value=expected)
    with patch(
        "app.adapters.persistence.node_reader.NodeRepository",
        return_value=repository,
    ):
        reader = ScopedNodeConnectionReader(context_factory(object()))
        assert await reader.get_connection(uuid4()) is not None
        assert await reader.get_connections_by_ids([uuid4()]) == expected
        assert await reader.get_connections_by_tags(["prod"]) == expected


async def test_script_reader_found_and_missing() -> None:
    script_id = uuid4()
    repository = MagicMock()
    repository.get_by_id = AsyncMock(
        side_effect=[
            SimpleNamespace(id=script_id, steps=[{"command_id": str(uuid4())}]),
            None,
        ]
    )
    with patch(
        "app.adapters.persistence.script_gateway.ScriptRepository",
        return_value=repository,
    ):
        reader = ScopedScriptDefinitionReader(context_factory(object()))
        found = await reader.get_definition(script_id)
        missing = await reader.get_definition(uuid4())
    assert found is not None
    assert len(found.steps) == 1
    assert missing is None


async def test_execution_writer_commits_short_transactions() -> None:
    execution_id = uuid4()
    repository = MagicMock()
    repository.create = AsyncMock(return_value=SimpleNamespace(id=execution_id))
    repository.update = AsyncMock()
    boundary = TransactionSpy()
    with patch(
        "app.adapters.persistence.script_gateway.ScriptExecutionRepository",
        return_value=repository,
    ):
        writer = ScopedScriptExecutionWriter(boundary)
        assert await writer.create_execution({"script_id": uuid4()}) == execution_id
        await writer.update_execution(execution_id, {"status": "completed"})
    repository.update.assert_awaited_once()
    assert boundary.transaction_entries == 2
    assert boundary.transaction_exits == 2
    assert boundary.transaction_active is False
