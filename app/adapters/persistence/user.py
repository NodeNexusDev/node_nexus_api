"""SQLAlchemy adapters for user and refresh token persistence."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.refresh_token import RefreshTokenRepository
from app.adapters.persistence.dao.user import UserRepository
from app.application.dto.user import UserCreateDTO, UserViewDTO
from app.models.user import UserModel

if TYPE_CHECKING:
    from app.application.ports.password_hasher import PasswordHasher


class SqlAlchemyUserGateway:
    """Implement user management ports."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        password_hasher: PasswordHasher,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._password_hasher = password_hasher

    async def get_user(self, user_id: UUID) -> UserViewDTO | None:
        async with self._sessionmaker() as session:
            user = await UserRepository(session).get_by_id(user_id)
            return self._to_view(user) if user is not None else None

    async def get_by_email(self, email: str) -> UserViewDTO | None:
        async with self._sessionmaker() as session:
            user = await UserRepository(session).get_by_email(email)
            return self._to_view(user) if user is not None else None

    async def list_users(self, offset: int, limit: int) -> list[UserViewDTO]:
        async with self._sessionmaker() as session:
            users = await UserRepository(session).get_all(offset, limit)
            return [self._to_view(u) for u in users]

    async def count_users(self) -> int:
        async with self._sessionmaker() as session:
            return await UserRepository(session).count()

    async def get_user_id_by_email(self, email: str) -> UUID | None:
        async with self._sessionmaker() as session:
            user = await UserRepository(session).get_by_email(email)
            return user.id if user is not None else None

    async def get_hashed_password(self, email: str) -> str | None:
        async with self._sessionmaker() as session:
            user = await UserRepository(session).get_by_email(email)
            return user.hashed_password if user is not None else None

    async def is_user_active(self, user_id: UUID) -> bool:
        async with self._sessionmaker() as session:
            user = await UserRepository(session).get_by_id(user_id)
            return user.is_active if user is not None else False

    async def is_superuser(self, user_id: UUID) -> bool:
        async with self._sessionmaker() as session:
            user = await UserRepository(session).get_by_id(user_id)
            return user.is_superuser if user is not None else False

    async def create_user(self, data: UserCreateDTO) -> UserViewDTO:
        async with self._sessionmaker.begin() as session:
            user = await UserRepository(session).create(
                {
                    "email": data.email,
                    "hashed_password": self._password_hasher.hash(data.password),
                    "is_superuser": data.is_superuser,
                }
            )
            return self._to_view(user)

    async def delete_user(self, user_id: UUID) -> bool:
        async with self._sessionmaker.begin() as session:
            return await UserRepository(session).delete(user_id)

    async def has_users(self) -> bool:
        """Check if any users exist."""
        async with self._sessionmaker() as session:
            count = await UserRepository(session).count()
            return count > 0

    @staticmethod
    def _to_view(user: UserModel) -> UserViewDTO:
        return UserViewDTO(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
        )


class SqlAlchemyRefreshTokenGateway:
    """Implement refresh token persistence ports."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_by_hash(self, token_hash: str) -> UUID | None:
        async with self._sessionmaker() as session:
            return await RefreshTokenRepository(session).get_user_id_by_hash(token_hash)

    async def create(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> None:
        async with self._sessionmaker.begin() as session:
            await RefreshTokenRepository(session).create(
                user_id, token_hash, expires_at
            )

    async def rotate(
        self,
        old_token_hash: str,
        user_id: UUID,
        new_token_hash: str,
        expires_at: datetime,
    ) -> bool:
        """Atomically consume one refresh token and persist its replacement."""
        async with self._sessionmaker.begin() as session:
            return await RefreshTokenRepository(session).rotate(
                old_token_hash,
                user_id,
                new_token_hash,
                expires_at,
            )

    async def delete(self, token_hash: str) -> bool:
        async with self._sessionmaker.begin() as session:
            return await RefreshTokenRepository(session).delete(token_hash)

    async def delete_by_user(self, user_id: UUID) -> int:
        async with self._sessionmaker.begin() as session:
            return await RefreshTokenRepository(session).delete_by_user(user_id)

    async def delete_expired_by_user(self, user_id: UUID) -> int:
        async with self._sessionmaker.begin() as session:
            return await RefreshTokenRepository(session).delete_expired_by_user(user_id)
