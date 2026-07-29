"""Persistence operations for script schedules."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.script_schedule import ScriptScheduleModel


class ScriptScheduleRepository:
    """Repository for the persistent scheduler source of truth."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_script_id(self, script_id: UUID) -> ScriptScheduleModel | None:
        result = await self._session.execute(
            select(ScriptScheduleModel).where(
                ScriptScheduleModel.script_id == script_id
            )
        )
        return result.scalar_one_or_none()

    async def list_enabled(self) -> list[ScriptScheduleModel]:
        result = await self._session.execute(
            select(ScriptScheduleModel).where(ScriptScheduleModel.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def upsert(
        self, script_id: UUID, data: dict[str, Any]
    ) -> ScriptScheduleModel:
        schedule = await self.get_by_script_id(script_id)
        if schedule is None:
            schedule = ScriptScheduleModel(script_id=script_id, **data)
            self._session.add(schedule)
        else:
            for key, value in data.items():
                setattr(schedule, key, value)
        await self._session.flush()
        return schedule

    async def delete_by_script_id(self, script_id: UUID) -> bool:
        schedule = await self.get_by_script_id(script_id)
        if schedule is None:
            return False
        await self._session.delete(schedule)
        await self._session.flush()
        await self._session.commit()
        return True

    async def commit(self) -> None:
        """Confirm persistent state before runtime scheduler registration."""
        await self._session.commit()
