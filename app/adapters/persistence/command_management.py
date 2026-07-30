"""Short-scope SQLAlchemy command management adapter."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.command import CommandRepository
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandListQueryDTO,
    CommandPageDTO,
    CommandParameterDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.application.dto.command_template import CommandTemplateDTO
from app.models.command import CommandModel


class SqlAlchemyCommandGateway:
    """Implement command query, mutation, and execution-template ports."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_command(self, command_id: UUID) -> CommandViewDTO | None:
        async with self._sessionmaker() as session:
            command = await CommandRepository(session).get_by_id(command_id)
            return self._to_view(command) if command is not None else None

    async def list_commands(self, query: CommandListQueryDTO) -> CommandPageDTO:
        async with self._sessionmaker() as session:
            repository = CommandRepository(session)
            tags = list(query.tags) or None
            commands = await repository.get_all(
                skip=query.offset,
                limit=query.limit,
                tags=tags,
            )
            total = await repository.count(tags=tags)
            return CommandPageDTO(
                items=tuple(self._to_view(command) for command in commands),
                total=total,
            )

    async def create_command(self, data: CommandCreateDTO) -> CommandViewDTO:
        async with self._sessionmaker.begin() as session:
            command = await CommandRepository(session).create(
                {
                    "name": data.name,
                    "description": data.description,
                    "command": data.command,
                    "parameters": [
                        self._parameter_to_dict(parameter)
                        for parameter in data.parameters
                    ],
                    "tags": list(data.tags),
                }
            )
            return self._to_view(command)

    async def update_command(
        self, command_id: UUID, data: CommandUpdateDTO
    ) -> CommandViewDTO | None:
        changes: dict[str, object] = dict(data.changes)
        parameters = changes.get("parameters")
        if isinstance(parameters, tuple):
            parameter_dtos = cast(tuple[CommandParameterDTO, ...], parameters)
            changes["parameters"] = [
                self._parameter_to_dict(parameter) for parameter in parameter_dtos
            ]
        tags = changes.get("tags")
        if isinstance(tags, tuple):
            changes["tags"] = list(tags)
        async with self._sessionmaker.begin() as session:
            command = await CommandRepository(session).update(command_id, changes)
            return self._to_view(command) if command is not None else None

    async def delete_command(self, command_id: UUID) -> bool:
        async with self._sessionmaker.begin() as session:
            repository = CommandRepository(session)
            command = await repository.get_by_id(command_id)
            if command is None:
                return False
            await session.delete(command)
            await session.flush()
            return True

    async def get_template(self, command_id: UUID) -> CommandTemplateDTO | None:
        async with self._sessionmaker() as session:
            command = await CommandRepository(session).get_by_id(command_id)
            if command is None:
                return None
            return CommandTemplateDTO(
                id=command.id,
                command=command.command,
                parameters=tuple(command.parameters or ()),
            )

    @staticmethod
    def _to_view(command: CommandModel) -> CommandViewDTO:
        return CommandViewDTO(
            id=command.id,
            name=command.name,
            description=command.description,
            command=command.command,
            parameters=tuple(
                CommandParameterDTO(**parameter)
                for parameter in (command.parameters or ())
            ),
            tags=tuple(command.tags or ()),
            created_at=command.created_at,
            updated_at=command.updated_at,
        )

    @staticmethod
    def _parameter_to_dict(parameter: CommandParameterDTO) -> dict[str, Any]:
        return {
            "name": parameter.name,
            "type": parameter.type,
            "required": parameter.required,
            "default": parameter.default,
            "description": parameter.description,
        }
