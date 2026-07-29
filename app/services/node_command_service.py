"""Use cases for connectivity checks and commands on a single node."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory
    from app.services.audit_service import AuditService

from app.application.dto.command_execution import CommandRequestDTO, CommandResultDTO
from app.core.connectors.ssh import command_fingerprint
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.repositories.node_repo import NodeRepository
from app.schemas.node import NodeResponse

audit = structlog.get_logger("audit")


class NodeCommandService:
    """Execute single-node SSH use cases."""

    def __init__(
        self,
        repository: NodeRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
        node_reader: NodeConnectionReader | None = None,
    ) -> None:
        self._repository = repository
        self._node_reader = node_reader
        self._audit = audit_service
        self._connector_factory = connector_factory

    async def _log(
        self,
        action: str,
        node_id: UUID,
        details: dict[str, Any],
    ) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def check_connectivity(self, node_id: UUID) -> NodeResponse:
        """Check SSH connectivity and update the persisted node status."""
        node = (
            await self._node_reader.get_connection(node_id)
            if self._node_reader
            else await self._repository.get_by_id(node_id)
        )
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        connector = get_connector_factory(self._connector_factory).create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=decrypt_value(node.password),
            ssh_key=decrypt_value(node.ssh_key),
        )

        try:
            async with connector:
                await connector.execute_command("echo ok")
            new_status = "active"
            audit.info("node.connectivity.ok", node_id=str(node_id))
        except ConnectionFailedError as exc:
            new_status = "unreachable"
            audit.warning(
                "node.connectivity.failed",
                node_id=str(node_id),
                error=str(exc),
            )
        except Exception as exc:
            new_status = "unreachable"
            audit.error(
                "node.connectivity.unexpected_error",
                node_id=str(node_id),
                error_type=type(exc).__name__,
                error=str(exc),
            )

        await self._log("check", node_id, {"status": new_status})
        updated = await self._repository.update(node_id, {"status": new_status})
        return NodeResponse.model_validate(updated)

    async def execute_command(
        self, node_id: UUID, data: CommandRequestDTO
    ) -> CommandResultDTO:
        """Execute a command on one node through SSH."""
        node = (
            await self._node_reader.get_connection(node_id)
            if self._node_reader
            else await self._repository.get_by_id(node_id)
        )
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        connector_kwargs = {
            "host": node.host,
            "port": node.port,
            "username": node.username,
            "password": decrypt_value(node.password),
            "ssh_key": decrypt_value(node.ssh_key),
        }
        if data.timeout is not None:
            connector_kwargs["timeout"] = data.timeout

        connector = get_connector_factory(self._connector_factory).create_ssh(
            **connector_kwargs
        )
        if self._audit:
            await self._audit.log_required(
                "execute.requested",
                node_id=node_id,
                details={"command_fingerprint": command_fingerprint(data.command)},
            )

        try:
            async with connector:
                stdout, stderr, exit_code = await connector.execute_command(
                    data.command
                )
            audit.info(
                "node.command.executed",
                node_id=str(node_id),
                command=data.command,
            )
            await self._log(
                "execute",
                node_id,
                {"command": data.command, "exit_code": exit_code},
            )
            return CommandResultDTO(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )
        except ConnectionFailedError as exc:
            audit.error(
                "node.command.failed",
                node_id=str(node_id),
                command=data.command,
                error=str(exc),
            )
            await self._log(
                "execute_failed",
                node_id,
                {"command": data.command, "error": str(exc)},
            )
            raise
        except Exception as exc:
            audit.error(
                "node.command.unexpected_error",
                node_id=str(node_id),
                command=data.command,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            await self._log(
                "execute_failed",
                node_id,
                {"command": data.command, "error": str(exc)},
            )
            raise ConnectionFailedError(
                f"Failed to execute command on node {node_id}: {exc}"
            ) from exc
