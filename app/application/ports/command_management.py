"""Command management persistence ports."""

from typing import Protocol
from uuid import UUID

from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandListQueryDTO,
    CommandPageDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)


class CommandReader(Protocol):
    """Read command management views."""

    async def get_command(self, command_id: UUID) -> CommandViewDTO | None:
        """Return one command."""
        ...

    async def list_commands(self, query: CommandListQueryDTO) -> CommandPageDTO:
        """Return one command page."""
        ...

    async def list_tags(self) -> list[str]:
        """Return all unique command tags."""
        ...


class CommandWriter(Protocol):
    """Persist command mutations."""

    async def create_command(self, data: CommandCreateDTO) -> CommandViewDTO:
        """Create and return a command."""
        ...

    async def update_command(
        self, command_id: UUID, data: CommandUpdateDTO
    ) -> CommandViewDTO | None:
        """Update and return a command when it exists."""
        ...

    async def delete_command(self, command_id: UUID) -> bool:
        """Delete a command and report whether it existed."""
        ...
