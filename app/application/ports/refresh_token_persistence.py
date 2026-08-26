"""Persistence ports for refresh tokens."""

from typing import Protocol
from uuid import UUID


class RefreshTokenReader(Protocol):
    """Read refresh tokens."""

    async def get_by_hash(self, token_hash: str) -> UUID | None:
        """Return user_id if token hash exists and is not expired."""
        ...


class RefreshTokenWriter(Protocol):
    """Persist refresh token mutations."""

    async def create(self, user_id: UUID, token_hash: str, expires_at: object) -> None:
        """Store a refresh token hash."""
        ...

    async def delete(self, token_hash: str) -> bool:
        """Delete a refresh token by hash."""
        ...

    async def delete_by_user(self, user_id: UUID) -> int:
        """Delete all refresh tokens for a user. Return count deleted."""
        ...

    async def delete_expired_by_user(self, user_id: UUID) -> int:
        """Delete expired refresh tokens for a user. Return count deleted."""
        ...
