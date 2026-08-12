"""Command execution history persistence ports."""

from typing import Protocol
from uuid import UUID

from app.application.dto.command_history import (
    BulkCommandHistoryQueryDTO,
    CommandHistoryCreateDTO,
    CommandHistoryDTO,
    CommandHistoryPageDTO,
    CommandHistoryQueryDTO,
)


class CommandHistoryWriter(Protocol):
    """Persist command execution records outside request transactions."""

    async def save(self, data: CommandHistoryCreateDTO) -> CommandHistoryDTO:
        """Save one command execution record and return its view."""
        ...


class CommandHistoryReader(Protocol):
    """Read command execution history outside request transactions."""

    async def list_by_node(
        self, query: CommandHistoryQueryDTO
    ) -> CommandHistoryPageDTO:
        """Return a paginated history page for one node."""
        ...

    async def list_by_batch(
        self, query: BulkCommandHistoryQueryDTO
    ) -> CommandHistoryPageDTO:
        """Return a paginated history page for one bulk batch."""
        ...

    async def get_by_id(self, execution_id: UUID) -> CommandHistoryDTO | None:
        """Return one execution record by ID."""
        ...
