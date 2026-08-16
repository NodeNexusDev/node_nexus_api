"""Node status history service."""

from __future__ import annotations

from app.application.dto.node_status_history import (
    NodeStatusChangeDTO,
    NodeStatusHistoryPageDTO,
    NodeStatusHistoryQueryDTO,
)
from app.application.ports.node_status_history import (
    NodeStatusHistoryReader,
    NodeStatusHistoryWriter,
)


class NodeStatusHistoryService:
    """Query and record node status changes."""

    def __init__(
        self,
        reader: NodeStatusHistoryReader,
        writer: NodeStatusHistoryWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def record_status_change(self, data: NodeStatusChangeDTO) -> None:
        """Write a status change to history."""
        await self._writer.save(data)

    async def get_history(
        self, query: NodeStatusHistoryQueryDTO
    ) -> NodeStatusHistoryPageDTO:
        """Return paginated status history for a node."""
        return await self._reader.list_by_node(query)
