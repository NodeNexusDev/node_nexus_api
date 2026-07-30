"""API-key management use cases."""

import secrets
from uuid import UUID

from app.application.dto.api_key import (
    APIKeyCreateDTO,
    APIKeyCreateResultDTO,
    APIKeyPageDTO,
    APIKeyPersistenceDTO,
    APIKeyUpdateDTO,
    APIKeyViewDTO,
)
from app.application.ports.api_key import APIKeyReader, APIKeyWriter
from app.application.ports.api_key_hasher import APIKeyHasher
from app.core.exceptions import APIKeyNotFoundError

_KEY_PREFIX_LENGTH = 8
_KEY_RANDOM_LENGTH = 48
_KEY_FORMAT = "nnk_"


def generate_api_key(hasher: APIKeyHasher) -> tuple[str, str, str]:
    """Generate one plain credential, hash, and display-safe prefix."""
    random_part = secrets.token_urlsafe(_KEY_RANDOM_LENGTH)[:_KEY_RANDOM_LENGTH]
    plain_key = f"{_KEY_FORMAT}{random_part}"
    return plain_key, hasher.hash(plain_key), plain_key[:_KEY_PREFIX_LENGTH]


class APIKeyManagementService:
    """Create, query, update, and revoke managed API keys."""

    def __init__(
        self,
        reader: APIKeyReader,
        writer: APIKeyWriter,
        hasher: APIKeyHasher,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._hasher = hasher

    async def create_api_key(self, data: APIKeyCreateDTO) -> APIKeyCreateResultDTO:
        plain_key, key_hash, key_prefix = generate_api_key(self._hasher)
        created = await self._writer.create_api_key(
            APIKeyPersistenceDTO(
                name=data.name,
                key_hash=key_hash,
                key_prefix=key_prefix,
                scope=data.scope,
            )
        )
        return APIKeyCreateResultDTO(
            id=created.id,
            name=created.name,
            plain_key=plain_key,
            key_prefix=created.key_prefix,
            created_at=created.created_at,
        )

    async def list_api_keys(self, page: int, size: int) -> APIKeyPageDTO:
        return await self._reader.list_api_keys((page - 1) * size, size)

    async def update_api_key(
        self, key_id: UUID, data: APIKeyUpdateDTO
    ) -> APIKeyViewDTO:
        updated = await self._writer.update_api_key(key_id, data)
        if updated is None:
            raise APIKeyNotFoundError(f"API key {key_id} not found")
        return updated

    async def revoke_api_key(self, key_id: UUID) -> None:
        if not await self._writer.revoke_api_key(key_id):
            raise APIKeyNotFoundError(f"API key {key_id} not found")
