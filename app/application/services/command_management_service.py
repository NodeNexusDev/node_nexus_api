"""Command management application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandListQueryDTO,
    CommandParameterDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.application.types import JsonObject
from app.core.exceptions import CommandNotFoundError

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.command_management import CommandReader, CommandWriter

audit = structlog.get_logger("audit")


class CommandManagementService:
    """Manage command templates through persistence ports."""

    def __init__(
        self,
        reader: CommandReader,
        writer: CommandWriter,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._audit = audit_service

    async def _log(self, action: str, details: JsonObject) -> None:
        if self._audit:
            await self._audit.log(action=action, details=details)

    async def get_command(self, command_id: UUID) -> CommandViewDTO:
        command = await self._reader.get_command(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        return command

    async def get_all_commands(
        self,
        page: int = 1,
        size: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> tuple[list[CommandViewDTO], int]:
        result = await self._reader.list_commands(
            CommandListQueryDTO(
                offset=(page - 1) * size,
                limit=size,
                tags=tuple(tags or ()),
                search=search,
            )
        )
        return list(result.items), result.total

    async def get_all_tags(self) -> list[str]:
        """Return all unique command tags."""
        return await self._reader.list_tags()

    async def create_command(self, data: CommandCreateDTO) -> CommandViewDTO:
        command = await self._writer.create_command(data)
        audit.info("command.create.ok", command_id=str(command.id), name=data.name)
        await self._log("create", {"entity": "command", "name": data.name})
        return command

    async def update_command(
        self, command_id: UUID, data: CommandUpdateDTO
    ) -> CommandViewDTO:
        command = await self._writer.update_command(command_id, data)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        audit.info("command.update.ok", command_id=str(command_id))
        await self._log("update", {"entity": "command", "id": str(command_id)})
        return command

    async def delete_command(self, command_id: UUID) -> bool:
        if await self._reader.get_command(command_id) is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        await self._log("delete", {"entity": "command", "id": str(command_id)})
        await self._writer.delete_command(command_id)
        audit.info("command.delete.ok", command_id=str(command_id))
        return True

    async def clone_command(
        self,
        command_id: UUID,
        new_name: str | None = None,
    ) -> CommandViewDTO:
        original = await self._reader.get_command(command_id)
        if original is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        clone_name = new_name or f"{original.name}-copy"
        clone_data = CommandCreateDTO(
            name=clone_name,
            description=original.description,
            command=original.command,
            parameters=tuple(
                CommandParameterDTO(
                    name=p.name,
                    type=p.type,
                    required=p.required,
                    default=p.default,
                    description=p.description,
                )
                for p in original.parameters
            ),
            tags=original.tags,
        )
        cloned = await self._writer.create_command(clone_data)
        audit.info(
            "command.clone.ok",
            command_id=str(cloned.id),
            source=str(command_id),
        )
        await self._log("clone", {"entity": "command", "source": str(command_id)})
        return cloned
