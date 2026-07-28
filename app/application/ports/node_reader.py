"""Node connection persistence port."""

from typing import Protocol
from uuid import UUID

from app.application.dto.node_connection import NodeConnectionDTO


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
