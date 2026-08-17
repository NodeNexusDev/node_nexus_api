from __future__ import annotations

from sqlalchemy import func, text, update
from sqlalchemy.dialects.postgresql import array as pg_array
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
            stmt_rm = (
                update(model)
                .where(text(":old_name = ANY(tags)"))
                .values(
                    tags=func.array_remove(model.tags, old_name),
                )
            )
            result = await self._session.execute(stmt_rm, {"old_name": old_name})
            total += result.rowcount  # ty: ignore[unresolved-attribute]
            stmt_add = (
                update(model)
                .where(text("NOT (:new_name = ANY(tags))"))
                .values(
                    tags=func.array_cat(model.tags, pg_array([new_name])),
                )
            )
            await self._session.execute(stmt_add, {"new_name": new_name})
        await self._session.flush()
        return total

    async def delete_tag(self, tag_name: str) -> int:
        total = 0
        for model in (NodeModel, CommandModel, ScriptModel):
            stmt = (
                update(model)
                .where(text(":del_tag = ANY(tags)"))
                .values(
                    tags=func.array_remove(model.tags, tag_name),
                )
            )
            result = await self._session.execute(stmt, {"del_tag": tag_name})
            total += result.rowcount  # ty: ignore[unresolved-attribute]
        await self._session.flush()
        return total
