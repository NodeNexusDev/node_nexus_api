"""Short-scope SQLAlchemy adapter for bulk node operations."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.node import NodeRepository
from app.application.dto.bulk_node_operation import (
    BulkNodeDeleteDTO,
    BulkNodeOperationResultDTO,
    BulkNodeTagOperationDTO,
)


class SqlAlchemyNodeBulkOperator:
    """Implement bulk node operations with operation-local sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def bulk_delete(self, data: BulkNodeDeleteDTO) -> BulkNodeOperationResultDTO:
        """Delete multiple nodes by IDs."""
        deleted_ids: list = []
        async with self._sessionmaker.begin() as session:
            repo = NodeRepository(session)
            for node_id in data.node_ids:
                if await repo.delete(node_id):
                    deleted_ids.append(node_id)
        return BulkNodeOperationResultDTO(
            affected=len(deleted_ids),
            node_ids=tuple(deleted_ids),
        )

    async def bulk_add_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Add tags to multiple nodes."""
        affected_ids: list = []
        async with self._sessionmaker.begin() as session:
            repo = NodeRepository(session)
            for node_id in data.node_ids:
                node = await repo.get_by_id(node_id)
                if node is not None:
                    existing = list(node.tags) if node.tags else []
                    changed = False
                    for tag in data.tags:
                        if tag not in existing:
                            existing.append(tag)
                            changed = True
                    if changed:
                        await repo.update(node_id, {"tags": tuple(existing)})
                        affected_ids.append(node_id)
        return BulkNodeOperationResultDTO(
            affected=len(affected_ids),
            node_ids=tuple(affected_ids),
        )

    async def bulk_remove_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Remove tags from multiple nodes."""
        affected_ids: list = []
        async with self._sessionmaker.begin() as session:
            repo = NodeRepository(session)
            for node_id in data.node_ids:
                node = await repo.get_by_id(node_id)
                if node is not None:
                    existing = list(node.tags) if node.tags else []
                    new_tags = [t for t in existing if t not in data.tags]
                    if len(new_tags) != len(existing):
                        await repo.update(node_id, {"tags": tuple(new_tags)})
                        affected_ids.append(node_id)
        return BulkNodeOperationResultDTO(
            affected=len(affected_ids),
            node_ids=tuple(affected_ids),
        )
