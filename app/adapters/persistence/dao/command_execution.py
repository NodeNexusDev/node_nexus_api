"""Internal SQLAlchemy DAO for command execution history."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command_execution import CommandExecutionModel


class CommandExecutionRepository:
    """Repository for command execution history records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: Mapping[str, object]) -> CommandExecutionModel:
        """Create a new command execution record."""
        execution = CommandExecutionModel(**data)
        self._session.add(execution)
        await self._session.flush()
        return execution

    async def get_by_id(self, execution_id: UUID) -> CommandExecutionModel | None:
        """Get one execution record by ID."""
        result = await self._session.execute(
            select(CommandExecutionModel).where(
                CommandExecutionModel.id == execution_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_node(
        self, node_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[CommandExecutionModel]:
        """Get paginated execution records for one node ordered by created_at DESC."""
        result = await self._session.execute(
            select(CommandExecutionModel)
            .where(CommandExecutionModel.node_id == node_id)
            .order_by(CommandExecutionModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_batch(
        self, batch_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[CommandExecutionModel]:
        """Get paginated records for one bulk batch ordered by created_at DESC."""
        result = await self._session.execute(
            select(CommandExecutionModel)
            .where(CommandExecutionModel.batch_id == batch_id)
            .order_by(CommandExecutionModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_node(self, node_id: UUID) -> int:
        """Count execution records for one node."""
        result = await self._session.execute(
            select(func.count(CommandExecutionModel.id)).where(
                CommandExecutionModel.node_id == node_id
            )
        )
        return result.scalar_one()

    async def count_by_batch(self, batch_id: UUID) -> int:
        """Count execution records for one bulk batch."""
        result = await self._session.execute(
            select(func.count(CommandExecutionModel.id)).where(
                CommandExecutionModel.batch_id == batch_id
            )
        )
        return result.scalar_one()
