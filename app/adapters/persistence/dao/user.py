"""Internal SQLAlchemy DAO for users."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserModel


class UserRepository:
    """Repository for users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: UUID) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        return result.scalar_one_or_none()

    async def get_all(self, offset: int, limit: int) -> list[UserModel]:
        result = await self._session.execute(
            select(UserModel)
            .order_by(UserModel.created_at, UserModel.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, data: Mapping[str, object]) -> UserModel:
        user = UserModel(**data)
        self._session.add(user)
        await self._session.flush()
        return user

    async def delete(self, id: UUID) -> bool:
        user = await self.get_by_id(id)
        if user is None:
            return False
        await self._session.delete(user)
        await self._session.flush()
        return True

    async def count(self) -> int:
        from sqlalchemy import func

        result = await self._session.execute(select(func.count(UserModel.id)))
        return int(result.scalar_one())
