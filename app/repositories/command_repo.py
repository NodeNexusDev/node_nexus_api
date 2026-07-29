"""Command repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command import CommandModel


class CommandRepository:
    """Repository for command templates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: UUID) -> CommandModel | None:
        result = await self._session.execute(
            select(CommandModel).where(CommandModel.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self, skip: int = 0, limit: int = 100, tags: list[str] | None = None
    ) -> list[CommandModel]:
        query = select(CommandModel)
        if tags:
            for tag in tags:
                query = query.where(CommandModel.tags.op("@>")([tag]))
        query = query.offset(skip).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count(self, tags: list[str] | None = None) -> int:
        query = select(func.count(CommandModel.id))
        if tags:
            for tag in tags:
                query = query.where(CommandModel.tags.op("@>")([tag]))
        result = await self._session.execute(query)
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
        await self._session.commit()
        return True
