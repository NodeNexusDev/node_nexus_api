"""API key service."""

import hashlib
import secrets
import uuid

from app.core.exceptions import APIKeyNotFoundError, APIKeyRevokedError
from app.repositories.api_key_repo import APIKeyRepository
from app.schemas.api_key import APIKeyCreated, APIKeyList

KEY_PREFIX_LENGTH = 8
KEY_RANDOM_LENGTH = 48
KEY_TOTAL_LENGTH = KEY_PREFIX_LENGTH + KEY_RANDOM_LENGTH
KEY_FORMAT = "nnk_"


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        Tuple of (plain_key, key_hash, key_prefix).
    """
    random_part = secrets.token_urlsafe(KEY_RANDOM_LENGTH)[:KEY_RANDOM_LENGTH]
    plain_key = f"{KEY_FORMAT}{random_part}"
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    key_prefix = plain_key[:KEY_PREFIX_LENGTH]
    return plain_key, key_hash, key_prefix


class APIKeyService:
    """Service for API key management."""

    def __init__(self, repository: APIKeyRepository) -> None:
        self._repo = repository

    async def create_api_key(self, name: str) -> APIKeyCreated:
        plain_key, key_hash, key_prefix = generate_api_key()
        model = await self._repo.create(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
        )
        return APIKeyCreated(
            id=model.id,
            name=model.name,
            key=plain_key,
            key_prefix=model.key_prefix,
            created_at=model.created_at,
        )

    async def validate_api_key(self, plain_key: str) -> None:
        """Validate an API key. Raises if invalid or revoked."""
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        model = await self._repo.get_by_key_hash(key_hash)
        if model is None:
            raise APIKeyNotFoundError("Invalid API key")
        if not model.is_active:
            raise APIKeyRevokedError("API key has been revoked")
        await self._repo.update_last_used(model.id)

    async def list_api_keys(self, page: int = 1, size: int = 20) -> APIKeyList:
        skip = (page - 1) * size
        items, total = await self._repo.list_all(offset=skip, limit=size)
        return APIKeyList(items=items, total=total)

    async def revoke_api_key(self, key_id: uuid.UUID) -> None:
        model = await self._repo.get_by_id(key_id)
        if model is None:
            raise APIKeyNotFoundError(f"API key {key_id} not found")
        await self._repo.revoke(key_id)
