"""Immutable DTOs for template registries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RegistryCreateDTO:
    """Immutable registry creation data."""

    owner: str
    name: str
    github_token: str | None = None
    default_branch: str = "main"


@dataclass(frozen=True, slots=True)
class RegistryViewDTO:
    """Public-safe registry view."""

    id: uuid.UUID
    owner: str
    name: str
    default_branch: str
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RegistryPageDTO:
    """Registry page."""

    items: tuple[RegistryViewDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class RegistrySyncItemDTO:
    """Result of syncing a single pack."""

    pack_id: str
    status: str
    error: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class RegistrySyncResultDTO:
    """Registry sync result."""

    registry_id: uuid.UUID
    total: int
    succeeded: int
    failed: int
    results: tuple[RegistrySyncItemDTO, ...]
