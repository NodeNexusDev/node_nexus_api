from __future__ import annotations

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
        pattern = f"%{query.q}%"
        limit = query.limit

        async with self._sessionmaker() as session:
            node_stmt = (
                select(NodeModel.id, NodeModel.name)
                .where(
                    or_(
                        NodeModel.name.ilike(pattern),
                        NodeModel.host.ilike(pattern),
                    )
                )
                .limit(limit)
            )
            cmd_stmt = (
                select(CommandModel.id, CommandModel.name)
                .where(
                    or_(
                        CommandModel.name.ilike(pattern),
                        CommandModel.description.ilike(pattern),
                    )
                )
                .limit(limit)
            )
            script_stmt = (
                select(ScriptModel.id, ScriptModel.name)
                .where(
                    or_(
                        ScriptModel.name.ilike(pattern),
                        ScriptModel.description.ilike(pattern),
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
                        "WHERE t ILIKE :pattern LIMIT :limit"
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
