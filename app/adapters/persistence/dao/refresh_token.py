"""Internal SQLAlchemy DAO for refresh tokens."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshTokenModel


class RefreshTokenRepository:
    """Repository for refresh tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_id_by_hash(self, token_hash: str) -> UUID | None:
        """Return user_id if token hash exists and is not expired."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(RefreshTokenModel.user_id).where(
                RefreshTokenModel.token_hash == token_hash,
                RefreshTokenModel.expires_at > now,
            )
        )
        row = result.first()
        return row[0] if row else None

    async def create(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> None:
        """Store a refresh token hash."""
        token = RefreshTokenModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()

    async def rotate(
        self,
        old_token_hash: str,
        user_id: UUID,
        new_token_hash: str,
        expires_at: datetime,
    ) -> bool:
        """Atomically replace a valid refresh token if it is still unused."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            delete(RefreshTokenModel)
            .where(
                RefreshTokenModel.token_hash == old_token_hash,
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.expires_at > now,
            )
            .returning(RefreshTokenModel.user_id)
        )
        consumed_user_id = result.scalar_one_or_none()
        result.close()
        if consumed_user_id is None:
            return False
        self._session.add(
            RefreshTokenModel(
                user_id=user_id,
                token_hash=new_token_hash,
                expires_at=expires_at,
            )
        )
        await self._session.flush()
        return True

    async def delete(self, token_hash: str) -> bool:
        """Delete a refresh token by hash."""
        result = await self._session.execute(
            delete(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        await self._session.flush()
        return result.rowcount > 0 if isinstance(result, CursorResult) else False

    async def delete_by_user(self, user_id: UUID) -> int:
        """Delete all refresh tokens for a user."""
        result = await self._session.execute(
            delete(RefreshTokenModel).where(RefreshTokenModel.user_id == user_id)
        )
        await self._session.flush()
        return result.rowcount if isinstance(result, CursorResult) else 0

    async def delete_expired_by_user(self, user_id: UUID) -> int:
        """Delete expired refresh tokens for a user."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            delete(RefreshTokenModel).where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.expires_at <= now,
            )
        )
        await self._session.flush()
        return result.rowcount if isinstance(result, CursorResult) else 0
