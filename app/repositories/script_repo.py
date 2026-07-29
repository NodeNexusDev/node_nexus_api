"""Script repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.script import ScriptModel
from app.repositories.base import IRepository


class ScriptRepository(IRepository[ScriptModel]):
    """Repository for scripts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: UUID) -> ScriptModel | None:
        result = await self._session.execute(
            select(ScriptModel).where(ScriptModel.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self, skip: int = 0, limit: int = 100, tags: list[str] | None = None
    ) -> list[ScriptModel]:
        query = select(ScriptModel)
        if tags:
            for tag in tags:
                query = query.where(ScriptModel.tags.op("@>")([tag]))
        query = query.offset(skip).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count(self, tags: list[str] | None = None) -> int:
        query = select(func.count(ScriptModel.id))
        if tags:
            for tag in tags:
                query = query.where(ScriptModel.tags.op("@>")([tag]))
        result = await self._session.execute(query)
        return result.scalar_one()

    async def create(self, data: dict[str, Any]) -> ScriptModel:
        script = ScriptModel(**data)
        self._session.add(script)
        await self._session.flush()
        return script

    async def update(self, id: UUID, data: dict[str, Any]) -> ScriptModel | None:
        script = await self.get_by_id(id)
        if script is None:
            return None
        for key, value in data.items():
            setattr(script, key, value)
        await self._session.flush()
        return script

    async def delete(self, id: UUID) -> bool:
        script = await self.get_by_id(id)
        if script is None:
            return False
        await self._session.delete(script)
        await self._session.flush()
        await self._session.commit()
        return True
