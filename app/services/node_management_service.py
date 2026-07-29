"""Node service for business logic."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.node_management import (
        NodeManagementReader,
        NodeManagementWriter,
    )
    from app.services.audit_service import AuditService

import structlog

from app.application.dto.node_management import (
    NodeCreateDTO,
    NodeCursorQueryDTO,
    NodeListQueryDTO,
    NodeTagDTO,
    NodeUpdateDTO,
    NodeUpdateValue,
)
from app.application.dto.node_view import NodeViewDTO
from app.core.exceptions import NodeNotFoundError
from app.core.security import encrypt

audit = structlog.get_logger("audit")

_SENSITIVE_FIELDS = ("password", "ssh_key")


class NodeManagementService:
    """Manage node persistence, tags, and pagination."""

    def __init__(
        self,
        reader: NodeManagementReader,
        writer: NodeManagementWriter,
        audit_service: AuditService | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
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
        node = await self._reader.get_node(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return node

    async def get_all_nodes(
        self,
        page: int = 1,
        size: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> tuple[list[NodeViewDTO], int]:
        """Get all nodes with total count, optionally filtered by tags and/or search."""
        result = await self._reader.list_nodes(
            NodeListQueryDTO(
                offset=(page - 1) * size,
                limit=size,
                tags=tuple(tags or ()),
                search=search,
            )
        )
        return list(result.items), result.total

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
        result = await self._reader.list_nodes_cursor(
            NodeCursorQueryDTO(
                cursor=cursor,
                limit=limit,
                tags=tuple(tags or ()),
                search=search,
            )
        )
        return list(result.items), result.next_cursor, result.has_more

    async def create_node(self, data: NodeCreateDTO) -> NodeViewDTO:
        """Create a new node. Encrypts sensitive fields before storage."""
        secured = replace(
            data,
            password=self._encrypt_value(data.password),
            ssh_key=self._encrypt_value(data.ssh_key),
        )
        node = await self._writer.create_node(secured)
        audit.info("node.create.ok", node_id=str(node.id), name=data.name)
        await self._log("create", node_id=node.id, details={"name": data.name})
        return node

    async def update_node(self, node_id: UUID, data: NodeUpdateDTO) -> NodeViewDTO:
        """Update an existing node. Encrypts sensitive fields before storage."""
        secured = NodeUpdateDTO(
            changes=tuple(
                (
                    field,
                    self._encrypt_value(value) if field in _SENSITIVE_FIELDS else value,
                )
                for field, value in data.changes
            )
        )
        node = await self._writer.update_node(node_id, secured)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        audit.info("node.update.ok", node_id=str(node_id))
        await self._log("update", node_id=node_id, details=dict(secured.changes))
        return node

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node."""
        node = await self._reader.get_node(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        await self._log("delete", node_id=node_id)
        await self._writer.delete_node(node_id)
        audit.info("node.delete.ok", node_id=str(node_id))
        return True

    async def get_nodes_by_tags(
        self, tags: list[str], skip: int = 0, limit: int = 100
    ) -> tuple[list[NodeViewDTO], int]:
        """Get nodes filtered by tags (nodes must have ALL specified tags)."""
        result = await self._reader.list_nodes(
            NodeListQueryDTO(
                offset=skip,
                limit=limit,
                tags=tuple(tags),
            )
        )
        return list(result.items), result.total

    async def get_all_tags(self) -> list[str]:
        """Get all unique tags across all nodes."""
        return await self._reader.list_tags()

    async def add_tag(self, node_id: UUID, data: NodeTagDTO) -> NodeViewDTO:
        """Add a tag to a node."""
        node = await self._reader.get_node(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        tags = list(node.tags) if node.tags else []
        if data.tag not in tags:
            tags.append(data.tag)
            updated = await self._writer.update_node(
                node_id,
                NodeUpdateDTO(changes=(("tags", tuple(tags)),)),
            )
            audit.info("node.tag.add", node_id=str(node_id), tag=data.tag)
            await self._log("add_tag", node_id=node_id, details={"tag": data.tag})
            if updated is None:
                raise NodeNotFoundError(f"Node {node_id} not found")
            return updated

        return node

    async def remove_tag(self, node_id: UUID, data: NodeTagDTO) -> NodeViewDTO:
        """Remove a tag from a node."""
        node = await self._reader.get_node(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        tags = list(node.tags) if node.tags else []
        if data.tag in tags:
            tags.remove(data.tag)
            updated = await self._writer.update_node(
                node_id,
                NodeUpdateDTO(changes=(("tags", tuple(tags)),)),
            )
            audit.info("node.tag.remove", node_id=str(node_id), tag=data.tag)
            await self._log("remove_tag", node_id=node_id, details={"tag": data.tag})
            if updated is None:
                raise NodeNotFoundError(f"Node {node_id} not found")
            return updated

        return node

    @staticmethod
    def _encrypt_value(value: NodeUpdateValue) -> NodeUpdateValue:
        """Encrypt a non-empty sensitive string."""
        return encrypt(value) if isinstance(value, str) and value else value
