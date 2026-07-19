"""Node repository implementation."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.node import NodeModel
from app.repositories.base import IRepository


class NodeRepository(IRepository[NodeModel]):
    """Node repository for database operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

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
        return result.scalar_one()

    async def get_by_tags(
        self, tags: list[str], skip: int = 0, limit: int = 100
    ) -> list[NodeModel]:
        """Get nodes that have ALL specified tags."""
        query = select(NodeModel)
        for tag in tags:
            query = query.where(NodeModel.tags.op("@>")([tag]))
        result = await self._session.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count_by_tags(self, tags: list[str]) -> int:
        """Count nodes that have ALL specified tags."""
        query = select(func.count(NodeModel.id))
        for tag in tags:
            query = query.where(NodeModel.tags.op("@>")([tag]))
        result = await self._session.execute(query)
        return result.scalar_one()

    async def get_all_tags(self) -> list[str]:
        """Get all unique tags across all nodes."""
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

    async def get_filtered(
        self,
        tags: list[str] | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[NodeModel]:
        """Get nodes filtered by tags and/or search (ILIKE on name/host)."""
        query = select(NodeModel)
        if tags:
            for tag in tags:
                query = query.where(NodeModel.tags.op("@>")([tag]))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    NodeModel.name.ilike(pattern),
                    NodeModel.host.ilike(pattern),
                )
            )
        result = await self._session.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count_filtered(
        self,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> int:
        """Count nodes matching filters."""
        query = select(func.count(NodeModel.id))
        if tags:
            for tag in tags:
                query = query.where(NodeModel.tags.op("@>")([tag]))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    NodeModel.name.ilike(pattern),
                    NodeModel.host.ilike(pattern),
                )
            )
        result = await self._session.execute(query)
        return result.scalar_one()

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
