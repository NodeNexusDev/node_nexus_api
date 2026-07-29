"""Node service for business logic."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.services.audit_service import AuditService

import structlog
from sqlalchemy.exc import IntegrityError

from app.application.dto.node_management import (
    NodeCreateDTO,
    NodeTagDTO,
    NodeUpdateDTO,
)
from app.application.dto.node_view import NodeViewDTO
from app.core.exceptions import NodeNameConflictError, NodeNotFoundError
from app.core.security import encrypt
from app.repositories.node_repo import NodeRepository

audit = structlog.get_logger("audit")

_SENSITIVE_FIELDS = ("password", "ssh_key")


class NodeManagementService:
    """Manage node persistence, tags, and pagination."""

    def __init__(
        self,
        repository: NodeRepository,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repository = repository
        self._audit = audit_service

    async def _log(
        self,
        action: str,
        node_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def get_node(self, node_id: UUID) -> NodeViewDTO:
        """Get a node by ID."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return self._to_view(node)

    async def get_all_nodes(
        self,
        page: int = 1,
        size: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> tuple[list[NodeViewDTO], int]:
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
        return [self._to_view(node) for node in nodes], total

    async def get_nodes_cursor(
        self,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> tuple[list[NodeViewDTO], tuple[datetime, UUID] | None, bool]:
        """Get nodes using cursor-based pagination.

        Returns (items, next_cursor, has_more).
        """
        nodes = await self._repository.get_list_cursor(
            cursor=cursor, limit=limit, tags=tags, search=search
        )
        has_more = len(nodes) > limit
        items = nodes[:limit]
        next_cursor = (
            (items[-1].created_at, items[-1].id) if has_more and items else None
        )
        return [self._to_view(node) for node in items], next_cursor, has_more

    async def create_node(self, data: NodeCreateDTO) -> NodeViewDTO:
        """Create a new node. Encrypts sensitive fields before storage."""
        raw: dict[str, object] = {
            "name": data.name,
            "host": data.host,
            "port": data.port,
            "connection_type": data.connection_type,
            "username": data.username,
            "password": data.password,
            "ssh_key": data.ssh_key,
            "docker_host": data.docker_host,
            "tags": list(data.tags),
        }
        self._encrypt_fields(raw)
        try:
            node = await self._repository.create(raw)
        except IntegrityError as exc:
            raise NodeNameConflictError(
                f"Node name '{data.name}' already exists"
            ) from exc
        audit.info("node.create.ok", node_id=str(node.id), name=data.name)
        await self._log("create", node_id=node.id, details={"name": data.name})
        return self._to_view(node)

    async def update_node(self, node_id: UUID, data: NodeUpdateDTO) -> NodeViewDTO:
        """Update an existing node. Encrypts sensitive fields before storage."""
        update_data: dict[str, object] = dict(data.changes)
        tags = update_data.get("tags")
        if isinstance(tags, tuple):
            update_data["tags"] = list(tags)
        self._encrypt_fields(update_data)
        node = await self._repository.update(node_id, update_data)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        audit.info("node.update.ok", node_id=str(node_id))
        await self._log("update", node_id=node_id, details=update_data)
        return self._to_view(node)

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
    ) -> tuple[list[NodeViewDTO], int]:
        """Get nodes filtered by tags (nodes must have ALL specified tags)."""
        nodes = await self._repository.get_by_tags(tags, skip=skip, limit=limit)
        total = await self._repository.count_by_tags(tags)
        return [self._to_view(node) for node in nodes], total

    async def get_all_tags(self) -> list[str]:
        """Get all unique tags across all nodes."""
        return await self._repository.get_all_tags()

    async def add_tag(self, node_id: UUID, data: NodeTagDTO) -> NodeViewDTO:
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
            if updated is None:
                raise NodeNotFoundError(f"Node {node_id} not found")
            return self._to_view(updated)

        return self._to_view(node)

    async def remove_tag(self, node_id: UUID, data: NodeTagDTO) -> NodeViewDTO:
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
            if updated is None:
                raise NodeNotFoundError(f"Node {node_id} not found")
            return self._to_view(updated)

        return self._to_view(node)

    @staticmethod
    def _to_view(node) -> NodeViewDTO:  # noqa: ANN001
        """Map a persistence record to public-safe application data."""
        return NodeViewDTO(
            id=node.id,
            name=node.name,
            host=node.host,
            port=node.port,
            connection_type=node.connection_type,
            status=node.status,
            username=node.username,
            docker_host=node.docker_host,
            tags=tuple(node.tags or ()),
            created_at=node.created_at,
            updated_at=node.updated_at,
        )

    @staticmethod
    def _encrypt_fields(data: dict[str, object]) -> None:
        """Encrypt sensitive fields in-place if they are non-empty strings."""
        for field in _SENSITIVE_FIELDS:
            value = data.get(field)
            if isinstance(value, str) and value:
                data[field] = encrypt(value)
