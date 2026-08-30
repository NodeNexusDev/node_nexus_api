"""Short-scope SQLAlchemy adapter for bulk node operations."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.bulk_node_operation import (
    BulkNodeCheckResultDTO,
    BulkNodeDeleteDTO,
    BulkNodeOperationResultDTO,
    BulkNodeTagOperationDTO,
)
from app.models.node import NodeModel


class SqlAlchemyNodeBulkOperator:
    """Implement bulk node operations with operation-local sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def bulk_delete(self, data: BulkNodeDeleteDTO) -> BulkNodeOperationResultDTO:
        """Delete multiple nodes by IDs."""
        async with self._sessionmaker.begin() as session:
            existing_stmt = select(NodeModel.id).where(NodeModel.id.in_(data.node_ids))
            existing = await session.execute(existing_stmt)
            existing_ids = tuple(row[0] for row in existing.all())
            if existing_ids:
                stmt = delete(NodeModel).where(NodeModel.id.in_(existing_ids))
                await session.execute(stmt)
        return BulkNodeOperationResultDTO(
            affected=len(existing_ids),
            node_ids=tuple(existing_ids),
        )

    async def bulk_add_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Add tags to multiple nodes."""
        async with self._sessionmaker.begin() as session:
            stmt = (
                select(NodeModel)
                .where(NodeModel.id.in_(data.node_ids))
                .with_for_update()
            )
            result = await session.execute(stmt)
            nodes = list(result.scalars().all())

            affected_ids: list[uuid.UUID] = []
            for node in nodes:
                existing = list(node.tags) if node.tags else []
                changed = False
                for tag in data.tags:
                    if tag not in existing:
                        existing.append(tag)
                        changed = True
                if changed:
                    node.tags = list(existing)
                    affected_ids.append(node.id)

        return BulkNodeOperationResultDTO(
            affected=len(affected_ids),
            node_ids=tuple(affected_ids),
        )

    async def bulk_remove_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Remove tags from multiple nodes."""
        async with self._sessionmaker.begin() as session:
            stmt = (
                select(NodeModel)
                .where(NodeModel.id.in_(data.node_ids))
                .with_for_update()
            )
            result = await session.execute(stmt)
            nodes = list(result.scalars().all())

            affected_ids: list[uuid.UUID] = []
            for node in nodes:
                existing = list(node.tags) if node.tags else []
                new_tags = [t for t in existing if t not in data.tags]
                if len(new_tags) != len(existing):
                    node.tags = list(new_tags)
                    affected_ids.append(node.id)

        return BulkNodeOperationResultDTO(
            affected=len(affected_ids),
            node_ids=tuple(affected_ids),
        )

    async def bulk_check(self, node_ids: tuple[str, ...]) -> BulkNodeCheckResultDTO:
        """Check which nodes exist by IDs."""
        if not node_ids:
            return BulkNodeCheckResultDTO(total=0, succeeded=0, failed=0, node_ids=())
        async with self._sessionmaker.begin() as session:
            stmt = select(NodeModel.id).where(NodeModel.id.in_(node_ids))
            result = await session.execute(stmt)
            existing_ids = [row[0] for row in result.all()]
        return BulkNodeCheckResultDTO(
            total=len(node_ids),
            succeeded=len(existing_ids),
            failed=len(node_ids) - len(existing_ids),
            node_ids=tuple(existing_ids),
        )
