"""Immutable command template used by remote execution."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CommandTemplateDTO:
    """Persistence-independent command template."""

    id: UUID
    command: str
    parameters: tuple[dict[str, Any], ...]
