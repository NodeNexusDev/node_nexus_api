"""Command template persistence port."""

from typing import Protocol
from uuid import UUID

from app.application.dto.command_template import CommandTemplateDTO


class CommandTemplateReader(Protocol):
    """Read immutable command templates in a short persistence scope."""

    async def get_template(self, command_id: UUID) -> CommandTemplateDTO | None:
        """Return a command template by ID."""
        ...
