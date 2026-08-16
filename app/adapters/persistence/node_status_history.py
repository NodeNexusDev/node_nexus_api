"""Short-scope SQLAlchemy adapter for node status history ports."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.node_status_history import (
    NodeStatusHistoryRepository,
)
from app.application.dto.node_status_history import (
    NodeStatusChangeDTO,
    NodeStatusHistoryPageDTO,
    NodeStatusHistoryQueryDTO,
    NodeStatusHistoryRecordDTO,
)
from app.models.node_status_history import NodeStatusHistoryModel


class SqlAlchemyNodeStatusHistoryGateway:
    """Implement node status history ports with operation-local sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def save(self, data: NodeStatusChangeDTO) -> None:
        """Persist a status change record in a short transaction."""
        async with self._sessionmaker.begin() as session:
            await NodeStatusHistoryRepository(session).create(
                {
                    "node_id": data.node_id,
                    "old_status": data.old_status,
                    "new_status": data.new_status,
                    "source": data.source,
                }
            )

    async def list_by_node(
        self, query: NodeStatusHistoryQueryDTO
    ) -> NodeStatusHistoryPageDTO:
        """Return one paginated page for a node outside the request scope."""
        async with self._sessionmaker() as session:
            repository = NodeStatusHistoryRepository(session)
            records = await repository.list_by_node(
                query.node_id,
                skip=query.offset,
                limit=query.limit,
            )
            total = await repository.count_by_node(query.node_id)
            return NodeStatusHistoryPageDTO(
                items=tuple(self._to_dto(record) for record in records),
                total=total,
            )

    @staticmethod
    def _to_dto(record: NodeStatusHistoryModel) -> NodeStatusHistoryRecordDTO:
        """Map an ORM record to an immutable application DTO."""
        return NodeStatusHistoryRecordDTO(
            id=record.id,
            node_id=record.node_id,
            old_status=record.old_status,
            new_status=record.new_status,
            source=record.source,
            changed_at=record.changed_at,
        )
