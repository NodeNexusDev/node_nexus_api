"""Command execution history application service."""

from __future__ import annotations

from uuid import UUID

from app.application.dto.command_history import (
    CommandHistoryPageDTO,
    CommandHistoryQueryDTO,
)
from app.application.ports.command_history import CommandHistoryReader


class CommandHistoryService:
    """Query command execution history for UI completeness."""

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
