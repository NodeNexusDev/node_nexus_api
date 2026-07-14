"""Command repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command import CommandModel
from app.repositories.base import IRepository


class CommandRepository(IRepository[CommandModel]):
    """Repository for command templates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: UUID) -> CommandModel | None:
        result = await self._session.execute(
            select(CommandModel).where(CommandModel.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[CommandModel]:
        result = await self._session.execute(
            select(CommandModel).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(CommandModel.id)))
        return result.scalar_one()

    async def create(self, data: dict[str, Any]) -> CommandModel:
        command = CommandModel(**data)
        self._session.add(command)
        await self._session.flush()
        return command

    async def update(self, id: UUID, data: dict[str, Any]) -> CommandModel | None:
        command = await self.get_by_id(id)
        if command is None:
            return None
        for key, value in data.items():
            setattr(command, key, value)
        await self._session.flush()
        return command

    async def delete(self, id: UUID) -> bool:
        command = await self.get_by_id(id)
        if command is None:
            return False
        await self._session.delete(command)
        await self._session.flush()
        return True
