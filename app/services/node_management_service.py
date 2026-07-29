"""Node service for business logic."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.services.audit_service import AuditService

import structlog
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import NodeNameConflictError, NodeNotFoundError
from app.core.security import encrypt
from app.repositories.node_repo import NodeRepository
from app.schemas.node import (
    NodeCreate,
    NodeResponse,
    NodeUpdate,
    TagAdd,
    TagRemove,
)

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
