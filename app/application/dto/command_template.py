"""Immutable command template used by remote execution."""

from dataclasses import dataclass
from uuid import UUID

from app.application.dto.command_management import CommandParameterDTO


@dataclass(frozen=True, slots=True)
class CommandTemplateDTO:
    """Persistence-independent command template."""

    id: UUID
    command: str
    parameters: tuple[CommandParameterDTO, ...]
