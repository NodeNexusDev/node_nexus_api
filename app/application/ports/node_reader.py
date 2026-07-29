"""Node connection persistence port."""

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from app.application.dto.node_connection import NodeConnectionDTO

if TYPE_CHECKING:
    from app.application.dto.node_view import NodeViewDTO


class NodeConnectionReader(Protocol):
    """Read immutable node connection data from persistence."""

    async def get_connection(self, node_id: UUID) -> NodeConnectionDTO | None:
        """Return connection data for one node."""
        ...

    async def get_connections_by_ids(
        self, node_ids: list[UUID]
    ) -> list[NodeConnectionDTO]:
        """Return connection data for the requested node IDs."""
        ...

    async def get_connections_by_tags(self, tags: list[str]) -> list[NodeConnectionDTO]:
        """Return connection data for nodes matching all tags."""
        ...


class NodeStatusWriter(Protocol):
    """Persist node connectivity status in a short transaction."""

    async def update_node_status(
        self, node_id: UUID, status: str
    ) -> "NodeViewDTO | None":
        """Update and return the public-safe node view."""
        ...
