from __future__ import annotations

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.base import escape_ilike
from app.application.dto.global_search import (
    GlobalSearchQueryDTO,
    GlobalSearchResultDTO,
    SearchResultItemDTO,
)
from app.models.command import CommandModel
from app.models.node import NodeModel
from app.models.script import ScriptModel


class SqlAlchemyGlobalSearchGateway:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def search(
        self,
        query: GlobalSearchQueryDTO,
    ) -> GlobalSearchResultDTO:
        escaped = escape_ilike(query.q)
        pattern = f"%{escaped}%"
        limit = query.limit

        async with self._sessionmaker() as session:
            node_stmt = (
                select(NodeModel.id, NodeModel.name)
                .where(
                    or_(
                        NodeModel.name.ilike(pattern, escape="\\"),
                        NodeModel.host.ilike(pattern, escape="\\"),
                    )
                )
                .limit(limit)
            )
            cmd_stmt = (
                select(CommandModel.id, CommandModel.name)
                .where(
                    or_(
                        CommandModel.name.ilike(pattern, escape="\\"),
                        CommandModel.description.ilike(pattern, escape="\\"),
                    )
                )
                .limit(limit)
            )
            script_stmt = (
                select(ScriptModel.id, ScriptModel.name)
                .where(
                    or_(
                        ScriptModel.name.ilike(pattern, escape="\\"),
                        ScriptModel.description.ilike(pattern, escape="\\"),
                    )
                )
                .limit(limit)
            )

            nodes = [
                SearchResultItemDTO(
                    id=row.id,
                    name=row.name,
                    entity_type="node",
                )
                for row in (await session.execute(node_stmt)).all()
            ]
            commands = [
                SearchResultItemDTO(
                    id=row.id,
                    name=row.name,
                    entity_type="command",
                )
                for row in (await session.execute(cmd_stmt)).all()
            ]
            scripts = [
                SearchResultItemDTO(
                    id=row.id,
                    name=row.name,
                    entity_type="script",
                )
                for row in (await session.execute(script_stmt)).all()
            ]

            tag_rows = (
                await session.execute(
                    text(
                        "SELECT DISTINCT t AS tag "
                        "FROM nodes, unnest(tags) AS t "
                        "WHERE t ILIKE :pattern ESCAPE '\\' LIMIT :limit"
                    ),
                    {"pattern": pattern, "limit": limit},
                )
            ).all()
            tags = [row.tag for row in tag_rows if row.tag]

        return GlobalSearchResultDTO(
            nodes=tuple(nodes),
            commands=tuple(commands),
            scripts=tuple(scripts),
            tags=tuple(tags),
        )
