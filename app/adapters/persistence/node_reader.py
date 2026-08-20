"""Short-scope SQLAlchemy implementation of the node reader port."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.node import NodeRepository
from app.application.dto.node_connection import NodeConnectionDTO


class ScopedNodeConnectionReader:
    """Read connection DTOs without retaining a session during remote I/O."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_connection(self, node_id: UUID) -> NodeConnectionDTO | None:
        async with self._sessionmaker() as session:
            return await NodeRepository(session).get_connection(node_id)

    async def get_connections_by_ids(
        self, node_ids: list[UUID]
    ) -> list[NodeConnectionDTO]:
        async with self._sessionmaker() as session:
            return await NodeRepository(session).get_connections_by_ids(node_ids)

    async def get_connections_by_tags(self, tags: list[str]) -> list[NodeConnectionDTO]:
        async with self._sessionmaker() as session:
            return await NodeRepository(session).get_connections_by_tags(tags)

    async def get_connections_by_type(
        self, connection_type: str
    ) -> list[NodeConnectionDTO]:
        async with self._sessionmaker() as session:
            repo = NodeRepository(session)
            return await repo.get_connections_by_type(connection_type)
