"""Unified command execution history query service."""

from uuid import UUID

from app.application.dto.command_history import (
    BulkCommandHistoryQueryDTO,
    CommandHistoryPageDTO,
    CommandHistoryQueryDTO,
)
from app.application.ports.command_history import CommandHistoryReader


class ExecutionHistoryService:
    """Query command execution history (single node and bulk batch)."""

    def __init__(self, reader: CommandHistoryReader) -> None:
        self._reader = reader

    async def get_node_history(
        self,
        node_id: UUID,
        page: int,
        size: int,
    ) -> CommandHistoryPageDTO:
        """Return one paginated page of a node's command execution history."""
        query = CommandHistoryQueryDTO(
            node_id=node_id,
            offset=(page - 1) * size,
            limit=size,
        )
        return await self._reader.list_by_node(query)

    async def get_batch_history(
        self, batch_id: UUID, *, page: int = 1, size: int = 20
    ) -> CommandHistoryPageDTO:
        """Return paginated execution records for one bulk batch."""
        offset = (page - 1) * size
        return await self._reader.list_by_batch(
            BulkCommandHistoryQueryDTO(
                batch_id=batch_id,
                offset=offset,
                limit=size,
            )
        )
