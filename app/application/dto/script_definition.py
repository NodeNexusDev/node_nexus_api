"""Immutable script definition used by remote execution."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ScriptDefinitionDTO:
    """Persistence-independent script pipeline."""

    id: UUID
    steps: tuple[dict[str, Any], ...]
