"""Immutable command template used by remote execution."""

from dataclasses import dataclass
from uuid import UUID

from app.application.dto.command_management import CommandParameterDTO
from app.core.constants import DEFAULT_TIMEOUT


@dataclass(frozen=True, slots=True)
class CommandTemplateDTO:
    """Persistence-independent command template."""

    id: UUID
    command: str
    parameters: tuple[CommandParameterDTO, ...]
    timeout: int = DEFAULT_TIMEOUT
