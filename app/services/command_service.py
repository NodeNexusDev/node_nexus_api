"""Command service for business logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.command_management import CommandReader, CommandWriter
    from app.application.ports.command_reader import CommandTemplateReader
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.node_reader import NodeConnectionReader
    from app.application.ports.remote_command import RemoteConnectorFactory

import structlog

from app.application.dto.command_execution import CommandResultDTO
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandExecuteRequestDTO,
    CommandListQueryDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
)
from app.core.template import render_command

audit = structlog.get_logger("audit")


class CommandService:
    """Service for command template operations."""

    def __init__(
        self,
        reader: CommandReader,
        writer: CommandWriter,
        command_reader: CommandTemplateReader,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._audit = audit_service
        self._connector_factory = connector_factory
        self._command_reader = command_reader
        self._node_reader = node_reader
        self._credential_cipher = credential_cipher

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
        command = await self._reader.get_command(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        return command

    async def get_all_commands(
        self, page: int = 1, size: int = 20, tags: list[str] | None = None
    ) -> tuple[list[CommandViewDTO], int]:
        """Get all commands with total count."""
        result = await self._reader.list_commands(
            CommandListQueryDTO(
                offset=(page - 1) * size,
                limit=size,
                tags=tuple(tags or ()),
            )
        )
        return list(result.items), result.total

    async def create_command(self, data: CommandCreateDTO) -> CommandViewDTO:
        """Create a new command template."""
        command = await self._writer.create_command(data)
        audit.info("command.create.ok", command_id=str(command.id), name=data.name)
        await self._log("create", details={"entity": "command", "name": data.name})
        return command

    async def update_command(
        self, command_id: UUID, data: CommandUpdateDTO
    ) -> CommandViewDTO:
        """Update an existing command template."""
        command = await self._writer.update_command(command_id, data)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        audit.info("command.update.ok", command_id=str(command_id))
        await self._log("update", details={"entity": "command", "id": str(command_id)})
        return command

    async def delete_command(self, command_id: UUID) -> bool:
        """Delete a command template."""
        command = await self._reader.get_command(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        await self._log("delete", details={"entity": "command", "id": str(command_id)})
        await self._writer.delete_command(command_id)
        audit.info("command.delete.ok", command_id=str(command_id))
        return True

    async def execute_command(
        self, command_id: UUID, data: CommandExecuteRequestDTO
    ) -> CommandResultDTO:
        """Execute a command template on a node."""
        command = await self._command_reader.get_template(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")

        parameters = list(command.parameters) if command.parameters else []
        rendered = render_command(command.command, parameters, dict(data.params))

        node = await self._node_reader.get_connection(data.node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {data.node_id} not found")

        password = self._credential_cipher.decrypt(node.password)
        ssh_key = self._credential_cipher.decrypt(node.ssh_key)
        connector = self._connector_factory.create_ssh(
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
