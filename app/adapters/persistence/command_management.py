"""Short-scope SQLAlchemy command management adapter."""

from typing import cast
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
from app.core.types import JsonObject, JsonValue
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
                search=query.search,
            )
            total = await repository.count(tags=tags, search=query.search)
            return CommandPageDTO(
                items=tuple(self._to_view(command) for command in commands),
                total=total,
            )

    async def list_tags(self) -> list[str]:
        """Return all unique command tags."""
        async with self._sessionmaker() as session:
            return await CommandRepository(session).get_all_tags()

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
                parameters=tuple(
                    self.parameter_from_json(parameter)
                    for parameter in (command.parameters or ())
                ),
            )

    @staticmethod
    def _to_view(command: CommandModel) -> CommandViewDTO:
        return CommandViewDTO(
            id=command.id,
            name=command.name,
            description=command.description,
            command=command.command,
            parameters=tuple(
                SqlAlchemyCommandGateway.parameter_from_json(parameter)
                for parameter in (command.parameters or ())
            ),
            tags=tuple(command.tags or ()),
            created_at=command.created_at,
            updated_at=command.updated_at,
        )

    @staticmethod
    def parameter_from_json(parameter: JsonObject | str) -> CommandParameterDTO:
        """Validate and map one persisted command parameter."""
        # Accept the legacy representation where parameters were stored as names.
        if isinstance(parameter, str):
            return CommandParameterDTO(name=parameter)
        name = parameter.get("name")
        parameter_type = parameter.get("type", "string")
        required = parameter.get("required", True)
        description = parameter.get("description")
        if not isinstance(name, str):
            raise ValueError("Stored command parameter name must be a string")
        if not isinstance(parameter_type, str) or parameter_type not in (
            "string",
            "integer",
            "boolean",
        ):
            raise ValueError("Stored command parameter type is invalid")
        if not isinstance(required, bool):
            raise ValueError("Stored command parameter required flag must be boolean")
        if description is not None and not isinstance(description, str):
            raise ValueError("Stored command parameter description must be a string")
        default: JsonValue = parameter.get("default")
        return CommandParameterDTO(
            name=name,
            type=parameter_type,
            required=required,
            default=default,
            description=description,
        )

    @staticmethod
    def _parameter_to_dict(parameter: CommandParameterDTO) -> JsonObject:
        return {
            "name": parameter.name,
            "type": parameter.type,
            "required": parameter.required,
            "default": parameter.default,
            "description": parameter.description,
        }
