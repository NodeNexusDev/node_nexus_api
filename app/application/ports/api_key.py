"""API-key authentication and management persistence ports."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.dto.api_key import (
    APIKeyAuthDTO,
    APIKeyPageDTO,
    APIKeyPersistenceDTO,
    APIKeyUpdateDTO,
    APIKeyViewDTO,
)


class APIKeyReader(Protocol):
    """Read credential-safe API-key projections."""

    async def get_auth_by_hash(self, key_hash: str) -> APIKeyAuthDTO | None:
        """Return authentication data for a hashed presented key."""
        ...

    async def get_api_key(self, key_id: UUID) -> APIKeyViewDTO | None:
        """Return one management view."""
        ...

    async def list_api_keys(self, offset: int, limit: int) -> APIKeyPageDTO:
        """Return one management page."""
        ...


class APIKeyWriter(Protocol):
    """Persist API-key mutations and authentication usage metadata."""

    async def create_api_key(self, data: APIKeyPersistenceDTO) -> APIKeyViewDTO:
        """Create a managed API key."""
        ...

    async def update_api_key(
        self, key_id: UUID, data: APIKeyUpdateDTO
    ) -> APIKeyViewDTO | None:
        """Update one key when it exists."""
        ...

    async def revoke_api_key(self, key_id: UUID) -> bool:
        """Revoke one key and report whether it existed."""
        ...

    async def touch_last_used(self, key_id: UUID, used_at: datetime) -> None:
        """Persist throttled authentication usage metadata."""
        ...
