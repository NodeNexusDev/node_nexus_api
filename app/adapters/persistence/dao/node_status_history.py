"""Internal SQLAlchemy DAO for node status history."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.node_status_history import NodeStatusHistoryModel


class NodeStatusHistoryRepository:
    """Repository for node status history records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict[str, Any]) -> NodeStatusHistoryModel:
        """Create a new status change record."""
        record = NodeStatusHistoryModel(**data)
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_by_node(
        self, node_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[NodeStatusHistoryModel]:
        """Get paginated status history for one node ordered by changed_at DESC."""
        result = await self._session.execute(
            select(NodeStatusHistoryModel)
            .where(NodeStatusHistoryModel.node_id == node_id)
            .order_by(NodeStatusHistoryModel.changed_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_node(self, node_id: UUID) -> int:
        """Count status history records for one node."""
        result = await self._session.execute(
            select(func.count(NodeStatusHistoryModel.id)).where(
                NodeStatusHistoryModel.node_id == node_id
            )
        )
        return result.scalar_one()
