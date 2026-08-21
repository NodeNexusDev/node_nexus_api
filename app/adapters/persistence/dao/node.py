"""Internal SQLAlchemy DAO for nodes."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.sql import Select
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.dao.base import escape_ilike
from app.application.dto.node_connection import NodeConnectionDTO
from app.models.node import NodeModel


class NodeRepository:
    """Node repository for database operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_connection_dto(node: NodeModel) -> NodeConnectionDTO:
        """Map a persistence model to immutable connection data."""
        return NodeConnectionDTO(
            id=node.id,
            name=node.name,
            host=node.host,
            port=node.port,
            connection_type=node.connection_type,
            username=node.username,
            password=node.password,
            ssh_key=node.ssh_key,
            passphrase=node.passphrase,
            docker_host=node.docker_host,
        )

    async def get_connection(self, node_id: UUID) -> NodeConnectionDTO | None:
        """Get immutable connection data for one node."""
        node = await self.get_by_id(node_id)
        if node is None:
            return None
        return self._to_connection_dto(node)

    async def get_connections_by_ids(
        self, node_ids: list[UUID]
    ) -> list[NodeConnectionDTO]:
        """Get immutable connection data for a list of node IDs."""
        nodes = await self.get_by_ids(node_ids)
        return [self._to_connection_dto(node) for node in nodes]

    async def get_connections_by_tags(self, tags: list[str]) -> list[NodeConnectionDTO]:
        """Get immutable connection data for nodes matching all tags."""
        nodes = await self.get_by_tags(tags)
        return [self._to_connection_dto(node) for node in nodes]

    async def get_connections_by_type(
        self, connection_type: str
    ) -> list[NodeConnectionDTO]:
        """Get immutable connection data for nodes of a given type."""
        result = await self._session.execute(
            select(NodeModel).where(NodeModel.connection_type == connection_type)
        )
        nodes = list(result.scalars().all())
        return [self._to_connection_dto(node) for node in nodes]

    async def get_by_id(self, id: UUID) -> NodeModel | None:
        """Get a node by ID."""
        result = await self._session.execute(
            select(NodeModel).where(NodeModel.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[NodeModel]:
        """Get all nodes with pagination."""
        result = await self._session.execute(
            select(NodeModel).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count total nodes."""
        result = await self._session.execute(select(func.count(NodeModel.id)))
        return int(result.scalar_one())

    async def get_by_tags(
        self, tags: list[str], skip: int = 0, limit: int = 100
    ) -> list[NodeModel]:
        """Get nodes that have ALL specified tags.

        Uses PostgreSQL @> operator — not testable with SQLite.
        """
        # pragma: no cover — PostgreSQL-only operator (@>)
        query = select(NodeModel)
        for tag in tags:
            query = query.where(NodeModel.tags.op("@>")([tag]))
        result = await self._session.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())

    async def get_all_tags(self) -> list[str]:
        """Get all unique tags across all nodes.

        Uses PostgreSQL unnest() — not testable with SQLite.
        """
        # pragma: no cover — PostgreSQL-only function (unnest)
        result = await self._session.execute(
            select(func.unnest(NodeModel.tags)).distinct()
        )
        return sorted(row[0] for row in result.all() if row[0])

    async def get_by_ids(self, ids: list[UUID]) -> list[NodeModel]:
        """Get nodes by a list of IDs."""
        if not ids:
            return []
        result = await self._session.execute(
            select(NodeModel).where(NodeModel.id.in_(ids))
        )
        return list(result.scalars().all())

    def _apply_filters(
        self,
        query: "Select[Any]",
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> "Select[Any]":
        """Apply tag and search filters to a query.

        Tag filtering uses PostgreSQL @> operator — not testable with SQLite.
        """
        if tags:
            # pragma: no cover — PostgreSQL-only operator (@>)
            for tag in tags:
                query = query.where(NodeModel.tags.op("@>")([tag]))
        if search:
            escaped = escape_ilike(search)
            pattern = f"%{escaped}%"
            query = query.where(
                or_(
                    NodeModel.name.ilike(pattern, escape="\\"),
                    NodeModel.host.ilike(pattern, escape="\\"),
                )
            )
        return query

    async def get_filtered(
        self,
        tags: list[str] | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[NodeModel]:
        """Get nodes filtered by tags and/or search (ILIKE on name/host).

        Tag filtering uses PostgreSQL @> operator — not testable with SQLite.
        """
        # pragma: no cover — PostgreSQL-only operator (@>) when tags provided
        query = self._apply_filters(select(NodeModel), tags=tags, search=search)
        result = await self._session.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count_filtered(
        self,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> int:
        """Count nodes matching filters.

        Tag filtering uses PostgreSQL @> operator — not testable with SQLite.
        """
        # pragma: no cover — PostgreSQL-only operator (@>) when tags provided
        query = self._apply_filters(
            select(func.count(NodeModel.id)), tags=tags, search=search
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def get_list_cursor(
        self,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> list[NodeModel]:
        """Get nodes using cursor-based pagination.

        Cursor is (created_at, id). Results are ordered by created_at DESC, id DESC.
        Fetches limit+1 to determine has_more.
        Uses explicit comparisons for SQLite compatibility (tuple_() with UUID fails).
        """
        query = self._apply_filters(select(NodeModel), tags=tags, search=search)
        if cursor is not None:
            cursor_dt, cursor_id = cursor
            query = query.where(
                or_(
                    NodeModel.created_at < cursor_dt,
                    and_(
                        NodeModel.created_at == cursor_dt,
                        NodeModel.id < cursor_id,
                    ),
                )
            )
        query = query.order_by(NodeModel.created_at.desc(), NodeModel.id.desc()).limit(
            limit + 1
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> NodeModel:
        """Create a new node."""
        node = NodeModel(**data)
        self._session.add(node)
        await self._session.flush()
        return node

    async def update(self, id: UUID, data: dict[str, Any]) -> NodeModel | None:
        """Update an existing node."""
        node = await self.get_by_id(id)
        if node is None:
            return None
        for key, value in data.items():
            setattr(node, key, value)
        await self._session.flush()
        return node

    async def delete(self, id: UUID) -> bool:
        """Delete a node by ID."""
        node = await self.get_by_id(id)
        if node is None:
            return False
        await self._session.delete(node)
        await self._session.flush()
        return True
