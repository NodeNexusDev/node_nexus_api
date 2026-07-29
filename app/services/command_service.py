"""Command service for business logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.command_reader import CommandTemplateReader
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory
    from app.repositories.node_repo import NodeRepository
    from app.services.audit_service import AuditService

import structlog

from app.application.dto.command_execution import CommandResultDTO
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandExecuteRequestDTO,
    CommandParameterDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
)
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.core.template import render_command
from app.repositories.command_repo import CommandRepository

audit = structlog.get_logger("audit")


class CommandService:
    """Service for command template operations."""

    def __init__(
        self,
        repository: CommandRepository,
        node_repository: NodeRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
        command_reader: CommandTemplateReader | None = None,
        node_reader: NodeConnectionReader | None = None,
    ):
        self._repository = repository
        self._node_repository = node_repository
        self._audit = audit_service
        self._connector_factory = connector_factory
        self._command_reader = command_reader
        self._node_reader = node_reader

    async def _log(
        self,
        action: str,
        node_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def get_command(self, command_id: UUID) -> CommandViewDTO:
        """Get a command by ID."""
        command = await self._repository.get_by_id(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        return self._to_response(command)

    async def get_all_commands(
        self, page: int = 1, size: int = 20, tags: list[str] | None = None
    ) -> tuple[list[CommandViewDTO], int]:
        """Get all commands with total count."""
        skip = (page - 1) * size
        commands = await self._repository.get_all(skip=skip, limit=size, tags=tags)
        total = await self._repository.count(tags=tags)
        return [self._to_response(c) for c in commands], total

    async def create_command(self, data: CommandCreateDTO) -> CommandViewDTO:
        """Create a new command template."""
        raw = {
            "name": data.name,
            "description": data.description,
            "command": data.command,
            "parameters": [
                self._parameter_to_dict(parameter) for parameter in data.parameters
            ],
            "tags": list(data.tags),
        }
        command = await self._repository.create(raw)
        audit.info("command.create.ok", command_id=str(command.id), name=data.name)
        await self._log("create", details={"entity": "command", "name": data.name})
        return self._to_response(command)

    async def update_command(
        self, command_id: UUID, data: CommandUpdateDTO
    ) -> CommandViewDTO:
        """Update an existing command template."""
        update_data: dict[str, object] = dict(data.changes)
        parameters = update_data.get("parameters")
        if isinstance(parameters, tuple):
            parameter_dtos = cast(tuple[CommandParameterDTO, ...], parameters)
            update_data["parameters"] = [
                self._parameter_to_dict(parameter) for parameter in parameter_dtos
            ]
        tags = update_data.get("tags")
        if isinstance(tags, tuple):
            update_data["tags"] = list(tags)
        command = await self._repository.update(command_id, update_data)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        audit.info("command.update.ok", command_id=str(command_id))
        await self._log("update", details={"entity": "command", "id": str(command_id)})
        return self._to_response(command)

    async def delete_command(self, command_id: UUID) -> bool:
        """Delete a command template."""
        command = await self._repository.get_by_id(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        await self._log("delete", details={"entity": "command", "id": str(command_id)})
        await self._repository.delete(command_id)
        audit.info("command.delete.ok", command_id=str(command_id))
        return True

    async def execute_command(
        self, command_id: UUID, data: CommandExecuteRequestDTO
    ) -> CommandResultDTO:
        """Execute a command template on a node."""
        command = (
            await self._command_reader.get_template(command_id)
            if self._command_reader
            else await self._repository.get_by_id(command_id)
        )
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")

        parameters = list(command.parameters) if command.parameters else []
        rendered = render_command(command.command, parameters, dict(data.params))

        node = (
            await self._node_reader.get_connection(data.node_id)
            if self._node_reader
            else await self._node_repository.get_by_id(data.node_id)
        )
        if node is None:
            raise NodeNotFoundError(f"Node {data.node_id} not found")

        password = decrypt_value(node.password)
        ssh_key = decrypt_value(node.ssh_key)
        connector = get_connector_factory(self._connector_factory).create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=password,
            ssh_key=ssh_key,
        )

        try:
            async with connector:
                stdout, stderr, exit_code = await connector.execute_command(rendered)
            audit.info(
                "command.executed",
                command_id=str(command_id),
                node_id=str(data.node_id),
                exit_code=exit_code,
            )
            await self._log(
                "execute",
                node_id=data.node_id,
                details={"command_id": str(command_id), "exit_code": exit_code},
            )
            return CommandResultDTO(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )
        except Exception as exc:
            audit.error(
                "command.execute.failed",
                command_id=str(command_id),
                node_id=str(data.node_id),
                error=str(exc),
            )
            await self._log(
                "execute_failed",
                node_id=data.node_id,
                details={"command_id": str(command_id), "error": str(exc)},
            )
            raise ConnectionFailedError(
                f"Failed to execute command on node {data.node_id}: {exc}"
            ) from exc

    @staticmethod
    def _to_response(command: Any) -> CommandViewDTO:
        parameters = tuple(
            CommandParameterDTO(**parameter) for parameter in (command.parameters or ())
        )
        return CommandViewDTO(
            id=command.id,
            name=command.name,
            description=command.description,
            command=command.command,
            parameters=parameters,
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
