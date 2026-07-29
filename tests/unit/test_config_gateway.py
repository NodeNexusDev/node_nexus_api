"""Tests for the coordinated SQLAlchemy configuration adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.persistence.config import SqlAlchemyConfigGateway
from app.application.dto.config import (
    CommandConfigDTO,
    ConfigTransferDTO,
    NodeConfigDTO,
    ScriptConfigDTO,
)


def _sessionmaker_for_export() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    sessionmaker = MagicMock()
    sessionmaker.return_value = context
    return sessionmaker, session


def _sessionmaker_for_import() -> tuple[MagicMock, MagicMock, AsyncMock]:
    session = MagicMock()
    transaction = AsyncMock()
    transaction.__aenter__.return_value = session
    transaction.__aexit__.return_value = False
    sessionmaker = MagicMock()
    sessionmaker.begin.return_value = transaction
    return sessionmaker, session, transaction


@pytest.mark.asyncio
async def test_export_maps_all_pages_to_transfer_dto() -> None:
    sessionmaker, session = _sessionmaker_for_export()
    node_repository = AsyncMock()
    command_repository = AsyncMock()
    script_repository = AsyncMock()
    node = MagicMock(
        host="10.0.0.1",
        port=22,
        connection_type="ssh",
        username="root",
        tags=["prod"],
    )
    node.name = "node-1"
    node_repository.get_all.side_effect = [
        [node],
        [],
    ]
    command_repository.get_all.return_value = []
    script_repository.get_all.return_value = []

    with (
        patch(
            "app.adapters.persistence.config.NodeRepository",
            return_value=node_repository,
        ) as node_factory,
        patch(
            "app.adapters.persistence.config.CommandRepository",
            return_value=command_repository,
        ),
        patch(
            "app.adapters.persistence.config.ScriptRepository",
            return_value=script_repository,
        ),
    ):
        result = await SqlAlchemyConfigGateway(
            sessionmaker,
            batch_size=1,
        ).export_config()

    assert result.nodes[0].name == "node-1"
    assert result.nodes[0].tags == ("prod",)
    assert result.commands == ()
    assert result.scripts == ()
    assert node_repository.get_all.await_count == 2
    node_factory.assert_called_once_with(session)
    command_repository.get_all.assert_awaited_once_with(skip=0, limit=1)


@pytest.mark.asyncio
async def test_import_uses_one_transaction_and_skips_duplicates() -> None:
    sessionmaker, session, _ = _sessionmaker_for_import()
    node_repository = AsyncMock()
    command_repository = AsyncMock()
    script_repository = AsyncMock()
    existing_node = MagicMock()
    existing_node.name = "existing"
    node_repository.get_all.return_value = [existing_node]
    command_repository.get_all.return_value = []
    script_repository.get_all.return_value = []
    data = ConfigTransferDTO(
        nodes=(
            NodeConfigDTO("existing", "10.0.0.1", 22, "ssh"),
            NodeConfigDTO("new", "10.0.0.2", 22, "ssh"),
        ),
        commands=(CommandConfigDTO("uptime", "uptime"),),
        scripts=(ScriptConfigDTO("deploy", steps=({"command": "uptime"},)),),
    )

    with (
        patch(
            "app.adapters.persistence.config.NodeRepository",
            return_value=node_repository,
        ) as node_factory,
        patch(
            "app.adapters.persistence.config.CommandRepository",
            return_value=command_repository,
        ) as command_factory,
        patch(
            "app.adapters.persistence.config.ScriptRepository",
            return_value=script_repository,
        ) as script_factory,
    ):
        result = await SqlAlchemyConfigGateway(sessionmaker).import_config(data)

    assert result.nodes_created == 1
    assert result.commands_created == 1
    assert result.scripts_created == 1
    assert result.errors == ("Node 'existing' already exists, skipped",)
    node_repository.create.assert_awaited_once()
    command_repository.create.assert_awaited_once()
    script_repository.create.assert_awaited_once()
    node_factory.assert_called_once_with(session)
    command_factory.assert_called_once_with(session)
    script_factory.assert_called_once_with(session)
    sessionmaker.begin.assert_called_once_with()


@pytest.mark.asyncio
async def test_import_exception_leaves_transaction_context() -> None:
    sessionmaker, _, transaction = _sessionmaker_for_import()
    node_repository = AsyncMock()
    command_repository = AsyncMock()
    script_repository = AsyncMock()
    node_repository.get_all.return_value = []
    command_repository.get_all.return_value = []
    command_repository.create.side_effect = RuntimeError("write failed")
    data = ConfigTransferDTO(
        nodes=(NodeConfigDTO("node", "10.0.0.1", 22, "ssh"),),
        commands=(CommandConfigDTO("uptime", "uptime"),),
    )

    with (
        patch(
            "app.adapters.persistence.config.NodeRepository",
            return_value=node_repository,
        ),
        patch(
            "app.adapters.persistence.config.CommandRepository",
            return_value=command_repository,
        ),
        patch(
            "app.adapters.persistence.config.ScriptRepository",
            return_value=script_repository,
        ),
        pytest.raises(RuntimeError, match="write failed"),
    ):
        await SqlAlchemyConfigGateway(sessionmaker).import_config(data)

    exit_args = transaction.__aexit__.await_args.args
    assert exit_args[0] is RuntimeError
    node_repository.create.assert_awaited_once()
