"""Short-scope SQLAlchemy adapter for persistent script schedules."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.schedule import ScheduleRequestDTO, ScheduleViewDTO
from app.models.script_schedule import ScriptScheduleModel


class SqlAlchemyScheduleGateway:
    """Implement schedule reader and writer ports with short transactions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_schedule(self, script_id: UUID) -> ScheduleViewDTO | None:
        async with self._sessionmaker() as session:
            schedule = await self._get_model(session, script_id)
            return self._to_view(schedule) if schedule is not None else None

    async def list_enabled_schedules(self) -> list[ScheduleViewDTO]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ScriptScheduleModel).where(ScriptScheduleModel.enabled.is_(True))
            )
            return [self._to_view(schedule) for schedule in result.scalars()]

    async def upsert_schedule(
        self, script_id: UUID, data: ScheduleRequestDTO
    ) -> ScheduleViewDTO:
        async with self._sessionmaker.begin() as session:
            schedule = await self._get_model(session, script_id)
            values = {
                "cron": data.cron,
                "timezone": data.timezone,
                "node_ids": [str(node_id) for node_id in data.node_ids],
                "params": dict(data.params),
                "enabled": True,
                "misfire_grace_seconds": data.misfire_grace_seconds,
                "operational_state": "pending_registration",
                "last_error_type": None,
                "next_run_at": None,
            }
            if schedule is None:
                schedule = ScriptScheduleModel(script_id=script_id, **values)
                session.add(schedule)
            else:
                for field, value in values.items():
                    setattr(schedule, field, value)
            await session.flush()
            return self._to_view(schedule)

    async def delete_schedule(self, script_id: UUID) -> bool:
        async with self._sessionmaker.begin() as session:
            schedule = await self._get_model(session, script_id)
            if schedule is None:
                return False
            await session.delete(schedule)
            await session.flush()
            return True

    async def mark_registration(
        self,
        script_id: UUID,
        *,
        state: str,
        error_type: str | None,
        next_run_at: datetime | None = None,
    ) -> None:
        await self._update_state(
            script_id,
            operational_state=state,
            last_error_type=error_type,
            next_run_at=next_run_at,
        )

    async def mark_started(self, script_id: UUID, occurred_at: datetime) -> None:
        await self._update_state(script_id, last_run_at=occurred_at)

    async def mark_succeeded(self, script_id: UUID, occurred_at: datetime) -> None:
        await self._update_state(
            script_id,
            last_success_at=occurred_at,
            last_error_type=None,
        )

    async def mark_failed(
        self, script_id: UUID, occurred_at: datetime, error_type: str
    ) -> None:
        await self._update_state(
            script_id,
            last_failure_at=occurred_at,
            last_error_type=error_type,
        )

    async def _update_state(self, script_id: UUID, **values: object) -> None:
        async with self._sessionmaker.begin() as session:
            await session.execute(
                update(ScriptScheduleModel)
                .where(ScriptScheduleModel.script_id == script_id)
                .values(**values)
            )

    @staticmethod
    async def _get_model(
        session: AsyncSession, script_id: UUID
    ) -> ScriptScheduleModel | None:
        result = await session.execute(
            select(ScriptScheduleModel).where(
                ScriptScheduleModel.script_id == script_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _to_view(schedule: ScriptScheduleModel) -> ScheduleViewDTO:
        return ScheduleViewDTO(
            id=schedule.id,
            script_id=schedule.script_id,
            cron=schedule.cron,
            timezone=schedule.timezone,
            node_ids=tuple(UUID(node_id) for node_id in schedule.node_ids),
            params=tuple((schedule.params or {}).items()),
            enabled=schedule.enabled,
            misfire_grace_seconds=schedule.misfire_grace_seconds,
            operational_state=schedule.operational_state,
            last_error_type=schedule.last_error_type,
            last_run_at=schedule.last_run_at,
            last_success_at=schedule.last_success_at,
            last_failure_at=schedule.last_failure_at,
            next_run_at=schedule.next_run_at,
        )
