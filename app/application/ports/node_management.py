"""Node management persistence ports."""

from typing import Protocol
from uuid import UUID

from app.application.dto.node_management import (
    NodeCreateDTO,
    NodeCursorPageDTO,
    NodeCursorQueryDTO,
    NodeListQueryDTO,
    NodePageDTO,
    NodeUpdateDTO,
)
from app.application.dto.node_view import NodeViewDTO


class NodeManagementReader(Protocol):
    """Read public-safe node management data."""

    async def get_node(self, node_id: UUID) -> NodeViewDTO | None:
        """Return one node."""
        ...

    async def list_nodes(self, query: NodeListQueryDTO) -> NodePageDTO:
        """Return one offset-based node page."""
        ...

    async def list_nodes_cursor(self, query: NodeCursorQueryDTO) -> NodeCursorPageDTO:
        """Return one keyset-based node page."""
        ...

    async def list_tags(self) -> list[str]:
        """Return all unique node tags."""
        ...


class NodeManagementWriter(Protocol):
    """Persist node management mutations."""

    async def create_node(self, data: NodeCreateDTO) -> NodeViewDTO:
        """Create and return a node."""
        ...

    async def update_node(
        self, node_id: UUID, data: NodeUpdateDTO
    ) -> NodeViewDTO | None:
        """Update and return a node when it exists."""
        ...

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node and report whether it existed."""
        ...
