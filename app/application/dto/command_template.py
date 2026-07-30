"""Immutable command template used by remote execution."""

from dataclasses import dataclass
from uuid import UUID

from app.application.types import JsonObject


@dataclass(frozen=True, slots=True)
class CommandTemplateDTO:
    """Persistence-independent command template."""

    id: UUID
    command: str
    parameters: tuple[JsonObject, ...]
