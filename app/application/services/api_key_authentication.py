"""API-key authentication query use case."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.application.ports.api_key import APIKeyReader, APIKeyWriter
from app.application.ports.api_key_hasher import APIKeyHasher
from app.core.exceptions import (
    APIKeyExpiredError,
    APIKeyRevokedError,
    AuthenticationError,
)

_LAST_USED_UPDATE_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Immutable authorization identity returned by authentication."""

    key_id: UUID
    key_prefix: str
    scope: str
    key_type: str = "managed"


class APIKeyAuthenticationService:
    """Authenticate presented credentials through safe persistence ports."""

    def __init__(
        self,
        reader: APIKeyReader,
        writer: APIKeyWriter,
        hasher: APIKeyHasher,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._hasher = hasher

    async def authenticate(self, plain_key: str) -> AuthenticatedPrincipal:
        record = await self._reader.get_auth_by_hash(self._hasher.hash(plain_key))
        if record is None:
            raise AuthenticationError("Invalid API key")
        if not record.is_active:
            raise APIKeyRevokedError("API key has been revoked")
        now = datetime.now(UTC)
        if record.expires_at is not None and record.expires_at < now:
            raise APIKeyExpiredError("API key has expired")
        if (
            record.last_used_at is None
            or now - record.last_used_at >= _LAST_USED_UPDATE_INTERVAL
        ):
            await self._writer.touch_last_used(record.id, now)
        return AuthenticatedPrincipal(
            key_id=record.id,
            key_prefix=record.key_prefix,
            scope=record.scope,
        )
