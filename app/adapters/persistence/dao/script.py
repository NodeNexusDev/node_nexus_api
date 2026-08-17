"""Internal SQLAlchemy DAO for scripts."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.dao.base import escape_ilike
from app.models.script import ScriptModel


class ScriptRepository:
    """Repository for scripts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: UUID) -> ScriptModel | None:
        result = await self._session.execute(
            select(ScriptModel).where(ScriptModel.id == id)
        )
        return result.scalar_one_or_none()

    def _apply_filters(
        self,
        query,
        tags: list[str] | None = None,
        search: str | None = None,
    ):
        if tags:
            for tag in tags:
                query = query.where(ScriptModel.tags.op("@>")([tag]))
        if search:
            escaped = escape_ilike(search)
            pattern = f"%{escaped}%"
            query = query.where(
                or_(
                    ScriptModel.name.ilike(pattern, escape="\\"),
                    ScriptModel.description.ilike(pattern, escape="\\"),
                )
            )
        return query

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> list[ScriptModel]:
        query = self._apply_filters(select(ScriptModel), tags=tags, search=search)
        query = query.offset(skip).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count(
        self, tags: list[str] | None = None, search: str | None = None
    ) -> int:
        query = self._apply_filters(
            select(func.count(ScriptModel.id)), tags=tags, search=search
        )
        result = await self._session.execute(query)
        return result.scalar_one()

    async def get_all_tags(self) -> list[str]:
        """Get all unique tags across all scripts.

        Uses PostgreSQL unnest() — not testable with SQLite.
        """
        # pragma: no cover — PostgreSQL-only function (unnest)
        result = await self._session.execute(
            select(func.unnest(ScriptModel.tags)).distinct()
        )
        return sorted(row[0] for row in result.all() if row[0])

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
        return True
