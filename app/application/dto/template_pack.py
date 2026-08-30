"""Immutable DTOs for template packs with assets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PackAssetCreateDTO:
    """Asset creation data."""

    path: str
    content_base64: str


@dataclass(frozen=True, slots=True)
class PackAssetDTO:
    """Persisted asset view."""

    id: uuid.UUID
    pack_id: uuid.UUID
    path: str
    size: int
    sha: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PackManifestDTO:
    """Manifest for local pack upload."""

    pack_id: str
    name: str
    version: str
    description: str | None = None
    author: str | None = None
    tags: tuple[str, ...] = ()
    manifest_sha: str | None = None


@dataclass(frozen=True, slots=True)
class PackCreateDTO:
    """Immutable pack creation data (local)."""

    manifest: PackManifestDTO
    commands: tuple[object, ...] = ()
    scripts: tuple[object, ...] = ()
    readme: str | None = None
    assets: tuple[PackAssetCreateDTO, ...] = ()
    registry_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class PackViewDTO:
    """Public-safe pack view."""

    id: uuid.UUID
    registry_id: uuid.UUID | None
    pack_id: str
    name: str
    description: str | None
    version: str
    author: str | None
    tags: tuple[str, ...]
    manifest_sha: str | None
    readme: str | None
    installed_version: str | None
    installed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PackDetailDTO:
    """Pack with assets."""

    pack: PackViewDTO
    assets: tuple[PackAssetDTO, ...] = ()
    commands: tuple[object, ...] = ()
    scripts: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class PackPageDTO:
    """Pack page."""

    items: tuple[PackViewDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class PackListQueryDTO:
    """Pack list query."""

    offset: int = 0
    limit: int = 20
    registry_id: uuid.UUID | None = None
    tag: str | None = None
    installed: bool | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True)
class PackInstallItemDTO:
    """Result of installing a single entity."""

    entity_type: str
    entity_id: uuid.UUID | None
    name: str
    status: str
    error: str = ""


@dataclass(frozen=True, slots=True)
class PackInstallResultDTO:
    """Bulk install result."""

    pack_id: uuid.UUID
    version: str
    total: int
    succeeded: int
    failed: int
    results: tuple[PackInstallItemDTO, ...]


@dataclass(frozen=True, slots=True)
class PackInstallationDTO:
    """Link pack -> entity."""

    id: uuid.UUID
    pack_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PackInstallationPageDTO:
    """Installation page."""

    items: tuple[PackInstallationDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class PackStatsBucketDTO:
    """Stats bucket for group_by."""

    group: str
    total: int
    installed: int = 0
    not_installed: int = 0


@dataclass(frozen=True, slots=True)
class PackStatsDTO:
    """Stats result."""

    total: int
    installed: int
    not_installed: int
    buckets: tuple[PackStatsBucketDTO, ...] = field(default_factory=tuple)
