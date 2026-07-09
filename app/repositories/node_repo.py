"""Node repository implementation."""

from uuid import UUID

from sqlalchemy import select
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

    async def create(self, data: dict) -> NodeModel:
        """Create a new node."""
        node = NodeModel(**data)
        self._session.add(node)
        await self._session.flush()
        return node

    async def update(self, id: UUID, data: dict) -> NodeModel | None:
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
