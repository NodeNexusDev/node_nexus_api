"""Immutable DTOs for script management use cases."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.application.types import JsonValue

ScriptStepType = Literal["inline", "command"]
ScriptFailurePolicy = Literal["stop", "continue"]


@dataclass(frozen=True, slots=True)
class ScriptStepDTO:
    """Persistence-independent definition of one script step."""

    label: str
    type: ScriptStepType
    command: str | None = None
    command_id: UUID | None = None
    params: tuple[tuple[str, JsonValue], ...] = ()
    on_failure: ScriptFailurePolicy = "stop"


@dataclass(frozen=True, slots=True)
class ScriptCreateDTO:
    """Application input for creating a script."""

    name: str
    steps: tuple[ScriptStepDTO, ...]
    description: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScriptUpdateDTO:
    """Application input preserving omitted and explicit-null fields."""

    changes: tuple[tuple[str, object], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ScriptViewDTO:
    """Public application view of a script."""

    id: UUID
    name: str
    description: str | None
    steps: tuple[ScriptStepDTO, ...]
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ScriptListQueryDTO:
    """Pagination and filtering input for script queries."""

    offset: int
    limit: int
    tags: tuple[str, ...] = ()
    search: str | None = None


@dataclass(frozen=True, slots=True)
class ScriptPageDTO:
    """One page of script views."""

    items: tuple[ScriptViewDTO, ...]
    total: int
