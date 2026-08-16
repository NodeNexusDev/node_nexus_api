from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command import CommandModel
from app.models.node import NodeModel
from app.models.script import ScriptModel


class SqlAlchemyTagManager:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rename_tag(self, old_name: str, new_name: str) -> int:
        total = 0
        for model in (NodeModel, CommandModel, ScriptModel):
            stmt = (
                update(model)
                .where(model.tags.any(old_name))
                .values(
                    tags=func.array_remove(model.tags, old_name),
                )
            )
            result = await self._session.execute(stmt)
            total += result.rowcount
            stmt_add = (
                update(model)
                .where(~model.tags.any(new_name))
                .values(
                    tags=func.array_cat(model.tags, func.array[new_name]),
                )
            )
            await self._session.execute(stmt_add)
        await self._session.flush()
        return total

    async def delete_tag(self, tag_name: str) -> int:
        total = 0
        for model in (NodeModel, CommandModel, ScriptModel):
            stmt = (
                update(model)
                .where(model.tags.any(tag_name))
                .values(
                    tags=func.array_remove(model.tags, tag_name),
                )
            )
            result = await self._session.execute(stmt)
            total += result.rowcount
        await self._session.flush()
        return total
