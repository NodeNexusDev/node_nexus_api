"""Node service for business logic."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.core.connectors.base import ConnectorFactory
    from app.services.audit_service import AuditService

import structlog

from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.core.security import encrypt
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.repositories.node_repo import NodeRepository
from app.schemas.node import (
    BulkCommandRequest,
    BulkCommandResult,
    BulkNodeResult,
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
        node = await self._repository.create(raw)
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
        """Check SSH connectivity to a node and update its status."""
        node_response = await self.get_node(node_id)
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        password = decrypt_value(node.password)
        ssh_key = decrypt_value(node.ssh_key)
        connector = get_connector_factory(self._connector_factory).create_ssh(
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
            audit.info("node.connectivity.ok", node_id=str(node_id))
            await self._log("check", node_id=node_id, details={"status": "active"})
        except ConnectionFailedError as exc:
            new_status = "unreachable"
            audit.warning(
                "node.connectivity.failed",
                node_id=str(node_id),
                error=str(exc),
            )
            await self._log("check", node_id=node_id, details={"status": "unreachable"})
        except Exception as exc:
            new_status = "unreachable"
            audit.error(
                "node.connectivity.unexpected_error",
                node_id=str(node_id),
                error_type=type(exc).__name__,
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

        password = decrypt_value(node.password)
        ssh_key = decrypt_value(node.ssh_key)

        connector_kwargs = {
            "host": node_response.host,
            "port": node_response.port,
            "username": node_response.username,
            "password": password,
            "ssh_key": ssh_key,
        }
        if data.timeout is not None:
            connector_kwargs["timeout"] = data.timeout

        connector = get_connector_factory(self._connector_factory).create_ssh(
            **connector_kwargs,
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
                node_id=node_id,
                details={"command": data.command, "exit_code": exit_code},
            )
            return CommandResult(
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
                node_id=node_id,
                details={"command": data.command, "error": str(exc)},
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
                node_id=node_id,
                details={"command": data.command, "error": str(exc)},
            )
            raise ConnectionFailedError(
                f"Failed to execute command on node {node_id}: {exc}"
            ) from exc

    async def get_node_metrics(self, node_id: UUID) -> NodeMetrics:
        """Get system metrics from a node via SSH."""
        node_response = await self.get_node(node_id)
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        password = decrypt_value(node.password)
        ssh_key = decrypt_value(node.ssh_key)
        connector = get_connector_factory(self._connector_factory).create_ssh(
            host=node_response.host,
            port=node_response.port,
            username=node_response.username,
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
        """Execute a command on multiple nodes in parallel."""
        # Resolve target nodes
        target_nodes = await self._resolve_targets(data)

        if not target_nodes:
            raise NodeNotFoundError("No nodes matched the given criteria")

        # Execute on all nodes in parallel
        tasks = [
            self._execute_on_single_node(node, data.command) for node in target_nodes
        ]
        results = await asyncio.gather(*tasks)

        succeeded = sum(1 for r in results if r.exit_code == 0)
        return BulkCommandResult(
            command=data.command,
            results=results,
            total=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
        )

    async def _resolve_targets(self, data: BulkCommandRequest) -> list[Any]:
        """Resolve target nodes from IDs and/or tags."""
        nodes_by_ids = None
        if data.node_ids:
            nodes_by_ids = await self._repository.get_by_ids(data.node_ids)

        nodes_by_tags = None
        if data.tags:
            nodes_by_tags = await self._repository.get_by_tags(data.tags)

        if nodes_by_ids is not None and nodes_by_tags is not None:
            tag_ids = {n.id for n in nodes_by_tags}
            return [n for n in nodes_by_ids if n.id in tag_ids]
        if nodes_by_ids is not None:
            return nodes_by_ids
        return nodes_by_tags or []

    async def _execute_on_single_node(self, node: Any, command: str) -> BulkNodeResult:
        """Execute a command on a single node, returning result (never raises)."""
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
                stdout, stderr, exit_code = await connector.execute_command(command)
            audit.info(
                "node.bulk.executed",
                node_id=str(node.id),
                command=command,
            )
            await self._log(
                "bulk_execute",
                node_id=node.id,
                details={"command": command, "exit_code": exit_code},
            )
            return BulkNodeResult(
                node_id=node.id,
                node_name=node.name,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )
        except ConnectionFailedError as exc:
            audit.error(
                "node.bulk.execute.failed",
                node_id=str(node.id),
                command=command,
                error=str(exc),
            )
            await self._log(
                "bulk_execute_failed",
                node_id=node.id,
                details={"command": command, "error": str(exc)},
            )
            return BulkNodeResult(
                node_id=node.id,
                node_name=node.name,
                stdout="",
                stderr=str(exc),
                exit_code=1,
            )
        except Exception as exc:
            audit.error(
                "node.bulk.execute.unexpected_error",
                node_id=str(node.id),
                command=command,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            await self._log(
                "bulk_execute_failed",
                node_id=node.id,
                details={"command": command, "error": str(exc)},
            )
            return BulkNodeResult(
                node_id=node.id,
                node_name=node.name,
                stdout="",
                stderr=str(exc),
                exit_code=1,
            )
