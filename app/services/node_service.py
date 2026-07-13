"""Node service for business logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.core.connectors.base import ConnectorFactory
    from app.services.audit_service import AuditService

import structlog

from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.core.security import decrypt, encrypt
from app.repositories.node_repo import NodeRepository
from app.schemas.node import (
    CommandRequest,
    CommandResult,
    NodeCreate,
    NodeResponse,
    NodeUpdate,
)

logger = structlog.get_logger()

_SENSITIVE_FIELDS = ("password", "ssh_key")


class NodeService:
    """Service for node operations."""

    def __init__(
        self,
        repository: NodeRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
    ):
        self._repository = repository
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

    async def get_node(self, node_id: UUID) -> NodeResponse:
        """Get a node by ID."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return NodeResponse.model_validate(node)

    async def get_all_nodes(
        self, skip: int = 0, limit: int = 100
    ) -> tuple[list[NodeResponse], int]:
        """Get all nodes with total count."""
        nodes = await self._repository.get_all(skip=skip, limit=limit)
        total = await self._repository.count()
        return [NodeResponse.model_validate(node) for node in nodes], total

    async def create_node(self, data: NodeCreate) -> NodeResponse:
        """Create a new node. Encrypts sensitive fields before storage."""
        raw = data.model_dump()
        self._encrypt_fields(raw)
        node = await self._repository.create(raw)
        await self._log("create", node_id=node.id, details={"name": data.name})
        return NodeResponse.model_validate(node)

    async def update_node(self, node_id: UUID, data: NodeUpdate) -> NodeResponse:
        """Update an existing node. Encrypts sensitive fields before storage."""
        update_data = data.model_dump(exclude_unset=True)
        self._encrypt_fields(update_data)
        node = await self._repository.update(node_id, update_data)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        await self._log("update", node_id=node_id, details=update_data)
        return NodeResponse.model_validate(node)

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node."""
        result = await self._repository.delete(node_id)
        if not result:
            raise NodeNotFoundError(f"Node {node_id} not found")
        await self._log("delete", node_id=node_id)
        return True

    @staticmethod
    def _encrypt_fields(data: dict[str, object]) -> None:
        """Encrypt sensitive fields in-place if they are non-empty strings."""
        for field in _SENSITIVE_FIELDS:
            value = data.get(field)
            if isinstance(value, str) and value:
                data[field] = encrypt(value)

    @staticmethod
    def _decrypt_value(value: str | None) -> str | None:
        """Decrypt a single value if it looks encrypted."""
        if not value:
            return value
        try:
            return decrypt(value)
        except Exception:
            return value

    def _get_connector_factory(self) -> ConnectorFactory:
        if self._connector_factory is None:
            raise RuntimeError("ConnectorFactory not configured")
        return self._connector_factory

    async def check_connectivity(self, node_id: UUID) -> NodeResponse:
        """Check SSH connectivity to a node and update its status."""
        node_response = await self.get_node(node_id)
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        password = self._decrypt_value(node.password)
        ssh_key = self._decrypt_value(node.ssh_key)
        connector = self._get_connector_factory().create_ssh(
            host=node_response.host,
            port=node_response.port,
            username=node_response.username,
            password=password,
            ssh_key=ssh_key,
        )

        try:
            async with connector:
                await connector.execute_command("echo ok")
            new_status = "active"
            logger.info("node.connectivity.ok", node_id=str(node_id))
            await self._log("check", node_id=node_id, details={"status": "active"})
        except Exception as exc:
            new_status = "unreachable"
            logger.warning(
                "node.connectivity.failed",
                node_id=str(node_id),
                error=str(exc),
            )
            await self._log("check", node_id=node_id, details={"status": "unreachable"})

        updated = await self._repository.update(node_id, {"status": new_status})
        return NodeResponse.model_validate(updated)

    async def execute_command(
        self, node_id: UUID, data: CommandRequest
    ) -> CommandResult:
        """Execute a command on a node via SSH."""
        node_response = await self.get_node(node_id)
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        password = self._decrypt_value(node.password)
        ssh_key = self._decrypt_value(node.ssh_key)
        connector = self._get_connector_factory().create_ssh(
            host=node_response.host,
            port=node_response.port,
            username=node_response.username,
            password=password,
            ssh_key=ssh_key,
        )

        try:
            async with connector:
                stdout, stderr, exit_code = await connector.execute_command(
                    data.command
                )
            logger.info(
                "node.command.executed",
                node_id=str(node_id),
                command=data.command,
            )
            await self._log(
                "execute",
                node_id=node_id,
                details={"command": data.command, "exit_code": exit_code},
            )
            return CommandResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )
        except Exception as exc:
            logger.error(
                "node.command.failed",
                node_id=str(node_id),
                command=data.command,
                error=str(exc),
            )
            await self._log(
                "execute_failed",
                node_id=node_id,
                details={"command": data.command, "error": str(exc)},
            )
            raise ConnectionFailedError(
                f"Failed to execute command on node {node_id}: {exc}"
            ) from exc
