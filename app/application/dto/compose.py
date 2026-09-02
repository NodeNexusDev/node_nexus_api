"""Immutable application DTOs for compose projects."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ComposeCreateDTO:
    """Immutable compose creation data."""

    node_id: UUID
    project_name: str
    compose: str
    env: tuple[tuple[str, str], ...] = ()
    template_pack_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComposeUpdateDTO:
    """Immutable compose update (partial)."""

    compose: str | None = None
    env: tuple[tuple[str, str], ...] | None = None
    template_pack_id: UUID | None = None
    has_env: bool = False
    has_template_pack_id: bool = False


ComposeUpdateValue = str | tuple[tuple[str, str], ...] | UUID | None


@dataclass(frozen=True, slots=True)
class ComposeViewDTO:
    """Public-safe compose project view."""

    id: UUID
    node_id: UUID
    project_name: str
    compose: str
    env: dict[str, str] | None
    template_pack_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ComposeListQueryDTO:
    """Immutable compose list query (cursor)."""

    node_id: UUID
    cursor: tuple[datetime, UUID] | None = None
    limit: int = 20


@dataclass(frozen=True, slots=True)
class ComposeUpRequestDTO:
    """Immutable compose up request."""

    node_id: UUID
    project_name: str
    pull: bool = False
    build: bool = False
    services: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComposeDownRequestDTO:
    """Immutable compose down request."""

    node_id: UUID
    project_name: str
    volumes: bool = False
    remove_orphans: bool = False
    timeout: int | None = None
    images: str | None = None


@dataclass(frozen=True, slots=True)
class ComposeExecRequestDTO:
    """Immutable compose exec request."""

    node_id: UUID
    project_name: str
    service: str
    command: str
    timeout: int = 30


@dataclass(frozen=True, slots=True)
class ComposeRunRequestDTO:
    """Immutable compose run request."""

    node_id: UUID
    project_name: str
    service: str
    command: str | None = None
    detached: bool = False
    timeout: int = 60


@dataclass(frozen=True, slots=True)
class ComposeServiceResultDTO:
    """Result of per-service compose verb."""

    service: str
    status: str
    output: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class ComposeBulkResultDTO:
    """Bulk result envelope for compose verbs."""

    total: int
    succeeded: int
    failed: int
    results: tuple[ComposeServiceResultDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ComposePsDTO:
    """Result of compose ps."""

    output: str
    containers: tuple[dict[str, str], ...] = ()


# Convenience re-export for id generation
def new_compose_id() -> UUID:
    """Generate a new compose project UUID."""
    return uuid.uuid4()
