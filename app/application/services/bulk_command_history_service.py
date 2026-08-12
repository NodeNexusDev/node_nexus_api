"""Query use case for bulk command execution history."""

from uuid import UUID

from app.application.dto.command_history import (
    BulkCommandHistoryQueryDTO,
    CommandHistoryPageDTO,
)
from app.application.ports.command_history import CommandHistoryReader


class BulkCommandHistoryService:
    """Read bulk command batch history."""

    def __init__(self, reader: CommandHistoryReader) -> None:
        self._reader = reader

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
