"""Node service for business logic."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory
    from app.services.audit_service import AuditService
    from app.services.node_bulk_command_service import NodeBulkCommandService
    from app.services.node_command_service import NodeCommandService

import structlog
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    ConnectionFailedError,
    NodeNameConflictError,
    NodeNotFoundError,
)
from app.core.security import encrypt
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.repositories.node_repo import NodeRepository
from app.schemas.node import (
    BulkCommandRequest,
    BulkCommandResult,
    CommandRequest,
    CommandResult,
    CpuMetrics,
    DiskMetrics,
    MemoryMetrics,
    NodeCreate,
    NodeMetrics,
    NodeResponse,
    NodeUpdate,
    TagAdd,
    TagRemove,
)

audit = structlog.get_logger("audit")

_SENSITIVE_FIELDS = ("password", "ssh_key")


class NodeService:
    """Service for node operations."""

    def __init__(
        self,
        repository: NodeRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
        node_reader: NodeConnectionReader | None = None,
        command_service: NodeCommandService | None = None,
        bulk_command_service: NodeBulkCommandService | None = None,
    ):
        self._repository = repository
        self._node_reader = node_reader
        self._audit = audit_service
        self._connector_factory = connector_factory
        self._command_service = command_service
        self._bulk_command_service = bulk_command_service

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
        self,
        page: int = 1,
        size: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> tuple[list[NodeResponse], int]:
        """Get all nodes with total count, optionally filtered by tags and/or search."""
        skip = (page - 1) * size
        if tags or search:
            nodes = await self._repository.get_filtered(
                tags=tags, search=search, skip=skip, limit=size
            )
            total = await self._repository.count_filtered(tags=tags, search=search)
        else:
            nodes = await self._repository.get_all(skip=skip, limit=size)
            total = await self._repository.count()
        return [NodeResponse.model_validate(node) for node in nodes], total

    async def get_nodes_cursor(
        self,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> tuple[list[NodeResponse], str | None, bool]:
        """Get nodes using cursor-based pagination.

        Returns (items, next_cursor, has_more).
        """
        nodes = await self._repository.get_list_cursor(
            cursor=cursor, limit=limit, tags=tags, search=search
        )
        has_more = len(nodes) > limit
        items = nodes[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            from app.schemas.common import encode_cursor

            next_cursor = encode_cursor(last.created_at, last.id)
        return [NodeResponse.model_validate(n) for n in items], next_cursor, has_more

    async def create_node(self, data: NodeCreate) -> NodeResponse:
        """Create a new node. Encrypts sensitive fields before storage."""
        raw = data.model_dump()
        self._encrypt_fields(raw)
        try:
            node = await self._repository.create(raw)
        except IntegrityError as exc:
            raise NodeNameConflictError(
                f"Node name '{data.name}' already exists"
            ) from exc
        audit.info("node.create.ok", node_id=str(node.id), name=data.name)
        await self._log("create", node_id=node.id, details={"name": data.name})
        return NodeResponse.model_validate(node)

    async def update_node(self, node_id: UUID, data: NodeUpdate) -> NodeResponse:
        """Update an existing node. Encrypts sensitive fields before storage."""
        update_data = data.model_dump(exclude_unset=True)
        self._encrypt_fields(update_data)
        node = await self._repository.update(node_id, update_data)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        audit.info("node.update.ok", node_id=str(node_id))
        await self._log("update", node_id=node_id, details=update_data)
        return NodeResponse.model_validate(node)

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        await self._log("delete", node_id=node_id)
        await self._repository.delete(node_id)
        audit.info("node.delete.ok", node_id=str(node_id))
        return True

    async def get_nodes_by_tags(
        self, tags: list[str], skip: int = 0, limit: int = 100
    ) -> tuple[list[NodeResponse], int]:
        """Get nodes filtered by tags (nodes must have ALL specified tags)."""
        nodes = await self._repository.get_by_tags(tags, skip=skip, limit=limit)
        total = await self._repository.count_by_tags(tags)
        return [NodeResponse.model_validate(node) for node in nodes], total

    async def get_all_tags(self) -> list[str]:
        """Get all unique tags across all nodes."""
        return await self._repository.get_all_tags()

    async def add_tag(self, node_id: UUID, data: TagAdd) -> NodeResponse:
        """Add a tag to a node."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        tags = list(node.tags) if node.tags else []
        if data.tag not in tags:
            tags.append(data.tag)
            updated = await self._repository.update(node_id, {"tags": tags})
            audit.info("node.tag.add", node_id=str(node_id), tag=data.tag)
            await self._log("add_tag", node_id=node_id, details={"tag": data.tag})
            return NodeResponse.model_validate(updated)

        return NodeResponse.model_validate(node)

    async def remove_tag(self, node_id: UUID, data: TagRemove) -> NodeResponse:
        """Remove a tag from a node."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        tags = list(node.tags) if node.tags else []
        if data.tag in tags:
            tags.remove(data.tag)
            updated = await self._repository.update(node_id, {"tags": tags})
            audit.info("node.tag.remove", node_id=str(node_id), tag=data.tag)
            await self._log("remove_tag", node_id=node_id, details={"tag": data.tag})
            return NodeResponse.model_validate(updated)

        return NodeResponse.model_validate(node)

    @staticmethod
    def _encrypt_fields(data: dict[str, object]) -> None:
        """Encrypt sensitive fields in-place if they are non-empty strings."""
        for field in _SENSITIVE_FIELDS:
            value = data.get(field)
            if isinstance(value, str) and value:
                data[field] = encrypt(value)

    async def check_connectivity(self, node_id: UUID) -> NodeResponse:
        """Delegate the legacy façade call to the single-node command service."""
        if self._command_service is None:
            raise RuntimeError("NodeCommandService is not configured")
        return await self._command_service.check_connectivity(node_id)

    async def execute_command(
        self, node_id: UUID, data: CommandRequest
    ) -> CommandResult:
        """Delegate the legacy façade call to the single-node command service."""
        if self._command_service is None:
            raise RuntimeError("NodeCommandService is not configured")
        return await self._command_service.execute_command(node_id, data)

    async def get_node_metrics(self, node_id: UUID) -> NodeMetrics:
        """Get system metrics from a node via SSH."""
        node = (
            await self._node_reader.get_connection(node_id)
            if self._node_reader
            else await self._repository.get_by_id(node_id)
        )
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

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
                # Get CPU info
                cpu_cmd = "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'"
                cpu_stdout, _, _ = await connector.execute_command(cpu_cmd)
                cpu_usage = float(cpu_stdout.strip()) if cpu_stdout.strip() else 0.0

                cores_cmd = "nproc"
                cores_stdout, _, _ = await connector.execute_command(cores_cmd)
                cores = int(cores_stdout.strip()) if cores_stdout.strip() else 1

                # Get memory info
                mem_cmd = "free -b | awk '/Mem:/ {print $2, $3, $4}'"
                mem_stdout, _, _ = await connector.execute_command(mem_cmd)
                mem_parts = mem_stdout.strip().split()
                if len(mem_parts) >= 3:
                    mem_total = int(mem_parts[0])
                    mem_used = int(mem_parts[1])
                    mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0.0
                else:
                    mem_total = 0
                    mem_used = 0
                    mem_percent = 0.0

                # Get disk info
                disk_cmd = "df -B1 / | awk 'NR==2 {print $2, $3, $4}'"
                disk_stdout, _, _ = await connector.execute_command(disk_cmd)
                disk_parts = disk_stdout.strip().split()
                if len(disk_parts) >= 3:
                    disk_total = int(disk_parts[0])
                    disk_used = int(disk_parts[1])
                    disk_percent = (
                        (disk_used / disk_total * 100) if disk_total > 0 else 0.0
                    )
                else:
                    disk_total = 0
                    disk_used = 0
                    disk_percent = 0.0

                # Get uptime
                uptime_cmd = "uptime -s"
                uptime_stdout, _, _ = await connector.execute_command(uptime_cmd)
                uptime_since = (
                    uptime_stdout.strip() if uptime_stdout.strip() else "unknown"
                )

            audit.info(
                "node.metrics.collected",
                node_id=str(node_id),
            )
            return NodeMetrics(
                cpu=CpuMetrics(usage_percent=cpu_usage, cores=cores),
                memory=MemoryMetrics(
                    total_bytes=mem_total,
                    used_bytes=mem_used,
                    percent=round(mem_percent, 2),
                ),
                disk=DiskMetrics(
                    total_bytes=disk_total,
                    used_bytes=disk_used,
                    percent=round(disk_percent, 2),
                ),
                uptime_since=uptime_since,
            )
        except ConnectionFailedError as exc:
            audit.error(
                "node.metrics.failed",
                node_id=str(node_id),
                error=str(exc),
            )
            raise
        except Exception as exc:
            audit.error(
                "node.metrics.unexpected_error",
                node_id=str(node_id),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise ConnectionFailedError(
                f"Failed to collect metrics from node {node_id}: {exc}"
            ) from exc

    async def bulk_execute_command(self, data: BulkCommandRequest) -> BulkCommandResult:
        """Delegate the legacy façade call to the bulk command service."""
        if self._bulk_command_service is None:
            raise RuntimeError("NodeBulkCommandService is not configured")
        return await self._bulk_command_service.execute(data)
