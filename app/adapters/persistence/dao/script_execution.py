"""Internal SQLAlchemy DAO for script executions."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.script_execution import ScriptExecutionModel


class ScriptExecutionRepository:
    """Repository for script execution records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: UUID) -> ScriptExecutionModel | None:
        result = await self._session.execute(
            select(ScriptExecutionModel).where(ScriptExecutionModel.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_script_id(
        self, script_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[ScriptExecutionModel]:
        result = await self._session.execute(
            select(ScriptExecutionModel)
            .where(ScriptExecutionModel.script_id == script_id)
            .order_by(ScriptExecutionModel.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_script_id(self, script_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count(ScriptExecutionModel.id)).where(
                ScriptExecutionModel.script_id == script_id
            )
        )
        return result.scalar_one()

    async def create(self, data: dict[str, Any]) -> ScriptExecutionModel:
        execution = ScriptExecutionModel(**data)
        self._session.add(execution)
        await self._session.flush()
        return execution

    async def update(
        self, id: UUID, data: dict[str, Any]
    ) -> ScriptExecutionModel | None:
        execution = await self.get_by_id(id)
        if execution is None:
            return None
        for key, value in data.items():
            setattr(execution, key, value)
        await self._session.flush()
        return execution
