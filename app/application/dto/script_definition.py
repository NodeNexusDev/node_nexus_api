"""Immutable script definition used by remote execution."""

from dataclasses import dataclass
from uuid import UUID

from app.application.types import JsonObject


@dataclass(frozen=True, slots=True)
class ScriptDefinitionDTO:
    """Persistence-independent script pipeline."""

    id: UUID
    steps: tuple[JsonObject, ...]
