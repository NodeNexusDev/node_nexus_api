"""Immutable API-key application contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class APIKeyViewDTO:
    """Management-safe API-key view without credential material."""

    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    scope: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class APIKeyAuthDTO:
    """Minimal record required to authenticate one presented key."""

    id: UUID
    key_prefix: str
    is_active: bool
    scope: str
    expires_at: datetime | None
    last_used_at: datetime | None


@dataclass(frozen=True, slots=True)
class APIKeyCreateDTO:
    """Requested API-key properties."""

    name: str
    scope: str = "read-write"


@dataclass(frozen=True, slots=True)
class APIKeyCreateResultDTO:
    """One-time create result; the plain key must never be persisted."""

    id: UUID
    name: str
    plain_key: str = field(repr=False)
    key_prefix: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class APIKeyPersistenceDTO:
    """Credential-bearing payload confined to the persistence boundary."""

    name: str
    key_hash: str = field(repr=False)
    key_prefix: str
    scope: str


@dataclass(frozen=True, slots=True)
class APIKeyUpdateDTO:
    """Partial management update."""

    changes: tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class APIKeyPageDTO:
    """One management page."""

    items: tuple[APIKeyViewDTO, ...]
    total: int
