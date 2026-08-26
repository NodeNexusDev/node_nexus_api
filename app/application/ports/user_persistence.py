"""Persistence ports for user management."""

from typing import Protocol
from uuid import UUID

from app.application.dto.user import UserCreateDTO, UserViewDTO


class UserReader(Protocol):
    """Read user management views."""

    async def get_user(self, user_id: UUID) -> UserViewDTO | None:
        """Return one user by ID."""
        ...

    async def get_by_email(self, email: str) -> UserViewDTO | None:
        """Return one user by email."""
        ...

    async def list_users(self) -> list[UserViewDTO]:
        """Return all users."""
        ...

    async def get_user_id_by_email(self, email: str) -> UUID | None:
        """Return user ID by email (for auth)."""
        ...

    async def get_hashed_password(self, email: str) -> str | None:
        """Return hashed password by email (for auth)."""
        ...

    async def is_user_active(self, user_id: UUID) -> bool:
        """Check if user is active."""
        ...

    async def is_superuser(self, user_id: UUID) -> bool:
        """Check if user is superuser."""
        ...


class UserWriter(Protocol):
    """Persist user mutations."""

    async def create_user(self, data: UserCreateDTO) -> UserViewDTO:
        """Create and return a user."""
        ...

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete a user and report whether it existed."""
        ...
