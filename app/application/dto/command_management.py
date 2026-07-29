"""Command management and execution application DTOs."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CommandParameterDTO:
    """Transport-independent command parameter definition."""

    name: str
    type: str = "string"
    required: bool = True
    default: Any = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CommandCreateDTO:
    """Immutable command creation data."""

    name: str
    command: str
    description: str | None = None
    parameters: tuple[CommandParameterDTO, ...] = ()
    tags: tuple[str, ...] = ()


CommandUpdateValue = str | tuple[CommandParameterDTO, ...] | tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class CommandUpdateDTO:
    """Immutable partial command update preserving explicit nulls."""

    changes: tuple[tuple[str, CommandUpdateValue], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class CommandViewDTO:
    """Public-safe command template view."""

    id: UUID
    name: str
    description: str | None
    command: str
    parameters: tuple[CommandParameterDTO, ...]
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CommandExecuteRequestDTO:
    """Immutable command template execution request."""

    node_id: UUID
    params: tuple[tuple[str, Any], ...] = ()
