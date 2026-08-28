"""Tests for the SQLAlchemy command management adapter."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.persistence.command_management import SqlAlchemyCommandGateway
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandListQueryDTO,
    CommandParameterDTO,
    CommandUpdateDTO,
)
from tests.unit.conftest import make_orm_command


def _sessionmaker() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    factory = MagicMock()
    factory.return_value = context
    factory.begin.return_value = context
    return factory, session


async def test_get_command_maps_orm_to_view() -> None:
    factory, _ = _sessionmaker()
    command = make_orm_command(
        parameters=[{"name": "path", "type": "string", "required": True}],
        tags=["ops"],
    )
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository_type.return_value.get_by_id = AsyncMock(return_value=command)
        result = await SqlAlchemyCommandGateway(factory).get_command(command.id)

    assert result is not None
    assert result.id == command.id
    assert result.parameters[0].name == "path"
    assert result.tags == ("ops",)


async def test_list_commands_maps_query_and_page() -> None:
    factory, _ = _sessionmaker()
    command = make_orm_command()
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.get_all = AsyncMock(return_value=[command])
        repository.count = AsyncMock(return_value=1)
        result = await SqlAlchemyCommandGateway(factory).list_commands(
            CommandListQueryDTO(offset=10, limit=5, tags=("ops",))
        )

    assert result.items[0].id == command.id
    assert result.total == 1
    repository.get_all.assert_awaited_once_with(
        skip=10, limit=5, tags=["ops"], search=None
    )
    repository.count.assert_awaited_once_with(tags=["ops"], search=None)


async def test_list_commands_with_search() -> None:
    factory, _ = _sessionmaker()
    command = make_orm_command()
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.get_all = AsyncMock(return_value=[command])
        repository.count = AsyncMock(return_value=1)
        result = await SqlAlchemyCommandGateway(factory).list_commands(
            CommandListQueryDTO(offset=0, limit=10, search="disk")
        )

    assert result.total == 1
    repository.get_all.assert_awaited_once_with(
        skip=0, limit=10, tags=None, search="disk"
    )
    repository.count.assert_awaited_once_with(tags=None, search="disk")


async def test_list_tags_delegates_to_repository() -> None:
    factory, _ = _sessionmaker()
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.get_all_tags = AsyncMock(return_value=["ops", "prod"])
        result = await SqlAlchemyCommandGateway(factory).list_tags()

    assert result == ["ops", "prod"]
    repository.get_all_tags.assert_awaited_once_with()


async def test_create_command_normalizes_immutable_values() -> None:
    factory, _ = _sessionmaker()
    command = make_orm_command()
    data = CommandCreateDTO(
        name="disk",
        command="df {path}",
        parameters=(CommandParameterDTO(name="path"),),
        tags=("ops",),
    )
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.create = AsyncMock(return_value=command)
        result = await SqlAlchemyCommandGateway(factory).create_command(data)

    assert result.id == command.id
    factory.begin.assert_called_once_with()
    assert repository.create.await_args is not None
    persisted = repository.create.await_args.args[0]
    assert persisted["parameters"][0]["name"] == "path"
    assert persisted["tags"] == ["ops"]


async def test_update_command_normalizes_immutable_values() -> None:
    factory, _ = _sessionmaker()
    command = make_orm_command()
    command_id = uuid.uuid4()
    data = CommandUpdateDTO(
        changes=(
            ("parameters", (CommandParameterDTO(name="path"),)),
            ("tags", ("ops",)),
        )
    )
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.update = AsyncMock(return_value=command)
        await SqlAlchemyCommandGateway(factory).update_command(command_id, data)

    assert repository.update.await_args is not None
    persisted = repository.update.await_args.args[1]
    assert persisted["parameters"][0]["name"] == "path"
    assert persisted["tags"] == ["ops"]


async def test_delete_command_uses_adapter_owned_transaction() -> None:
    factory, session = _sessionmaker()
    command = make_orm_command()
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository_type.return_value.get_by_id = AsyncMock(return_value=command)
        deleted = await SqlAlchemyCommandGateway(factory).delete_command(command.id)

    assert deleted is True
    factory.begin.assert_called_once_with()
    session.delete.assert_awaited_once_with(command)
    session.flush.assert_awaited_once_with()


async def test_get_template_maps_execution_dto() -> None:
    factory, _ = _sessionmaker()
    command = make_orm_command(command="true")
    with patch(
        "app.adapters.persistence.command_management.CommandRepository"
    ) as repository_type:
        repository_type.return_value.get_by_id = AsyncMock(return_value=command)
        result = await SqlAlchemyCommandGateway(factory).get_template(command.id)

    assert result is not None
    assert result.command == "true"
