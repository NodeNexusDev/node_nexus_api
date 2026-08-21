"""Internal SQLAlchemy DAO for command templates."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.adapters.persistence.dao.base import escape_ilike
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

    def _apply_filters(
        self,
        query: Select[Any],
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> Select[Any]:
        if tags:
            for tag in tags:
                query = query.where(CommandModel.tags.op("@>")([tag]))
        if search:
            escaped = escape_ilike(search)
            pattern = f"%{escaped}%"
            query = query.where(
                or_(
                    CommandModel.name.ilike(pattern, escape="\\"),
                    CommandModel.description.ilike(pattern, escape="\\"),
                )
            )
        return query

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> list[CommandModel]:
        query = self._apply_filters(select(CommandModel), tags=tags, search=search)
        query = query.offset(skip).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count(
        self, tags: list[str] | None = None, search: str | None = None
    ) -> int:
        query = self._apply_filters(
            select(func.count(CommandModel.id)), tags=tags, search=search
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def get_all_tags(self) -> list[str]:
        """Get all unique tags across all commands.

        Uses PostgreSQL unnest() — not testable with SQLite.
        """
        # pragma: no cover — PostgreSQL-only function (unnest)
        result = await self._session.execute(
            select(func.unnest(CommandModel.tags)).distinct()
        )
        return sorted(row[0] for row in result.all() if row[0])

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
