"""Immutable script definition used by remote execution."""

from dataclasses import dataclass
from uuid import UUID

from app.application.types import JsonObject
from app.core.constants import DEFAULT_TIMEOUT


@dataclass(frozen=True, slots=True)
class ScriptDefinitionDTO:
    """Persistence-independent script pipeline."""

    id: UUID
    steps: tuple[JsonObject, ...]
    timeout: int = DEFAULT_TIMEOUT
