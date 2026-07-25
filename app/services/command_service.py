"""Command service for business logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.core.connectors.base import ConnectorFactory
    from app.repositories.node_repo import NodeRepository
    from app.services.audit_service import AuditService

import structlog

from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
)
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.core.template import render_command
from app.repositories.command_repo import CommandRepository
from app.schemas.command import (
    CommandCreate,
    CommandExecuteRequest,
    CommandResponse,
    CommandResult,
    CommandUpdate,
)

audit = structlog.get_logger("audit")


class CommandService:
    """Service for command template operations."""

    def __init__(
        self,
        repository: CommandRepository,
        node_repository: NodeRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
    ):
        self._repository = repository
        self._node_repository = node_repository
        self._audit = audit_service
        self._connector_factory = connector_factory

    async def _log(
        self,
        action: str,
        node_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def get_command(self, command_id: UUID) -> CommandResponse:
        """Get a command by ID."""
        command = await self._repository.get_by_id(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        return self._to_response(command)

    async def get_all_commands(
        self, page: int = 1, size: int = 20
    ) -> tuple[list[CommandResponse], int]:
        """Get all commands with total count."""
        skip = (page - 1) * size
        commands = await self._repository.get_all(skip=skip, limit=size)
        total = await self._repository.count()
        return [self._to_response(c) for c in commands], total

    async def create_command(self, data: CommandCreate) -> CommandResponse:
        """Create a new command template."""
        raw = data.model_dump()
        command = await self._repository.create(raw)
        audit.info("command.create.ok", command_id=str(command.id), name=data.name)
        await self._log("create", details={"entity": "command", "name": data.name})
        return self._to_response(command)

    async def update_command(
        self, command_id: UUID, data: CommandUpdate
    ) -> CommandResponse:
        """Update an existing command template."""
        update_data = data.model_dump(exclude_unset=True)
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
        self, command_id: UUID, data: CommandExecuteRequest
    ) -> CommandResult:
        """Execute a command template on a node."""
        command = await self._repository.get_by_id(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")

        parameters = command.parameters if command.parameters else []
        rendered = render_command(command.command, parameters, data.params)

        node = await self._node_repository.get_by_id(data.node_id)
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
            return CommandResult(
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
    def _to_response(command: Any) -> CommandResponse:
        parameters = command.parameters if command.parameters else []
        return CommandResponse(
            id=command.id,
            name=command.name,
            description=command.description,
            command=command.command,
            parameters=parameters,
            created_at=command.created_at,
            updated_at=command.updated_at,
        )
