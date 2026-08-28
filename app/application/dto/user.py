"""Immutable DTOs for user management use cases."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserViewDTO:
    """Public application view of a user."""

    id: UUID
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UserCreateDTO:
    """Application input for creating a user."""

    email: str
    password: str = field(repr=False)
    is_superuser: bool = False


@dataclass(frozen=True, slots=True)
class UserPageDTO:
    """Bounded page of users."""

    items: tuple[UserViewDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class AuthIdentityDTO:
    """Unified authentication result."""

    type: str  # "jwt", "api_key", "master"
    user_id: UUID | None = None
    email: str | None = None
    is_superuser: bool = False
    key_id: UUID | None = None
    key_prefix: str | None = None
    scope: str | None = None
