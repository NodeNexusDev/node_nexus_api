"""Application service for persistent script schedules."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from app.core.exceptions import (
    NodeNotFoundError,
    ScheduleNotFoundError,
    SchedulePersistenceError,
    ScheduleValidationError,
    ScriptNotFoundError,
)
from app.core.metrics import (
    SCHEDULER_ACTIVE,
    SCHEDULER_REGISTRATION_FAILURES,
    SCHEDULER_RESTORED,
)
from app.core.scheduler import ScriptScheduler
from app.repositories.node_repo import NodeRepository
from app.repositories.script_repo import ScriptRepository
from app.repositories.script_schedule_repo import ScriptScheduleRepository
from app.schemas.scheduler import ScheduledJob, ScheduleRequest


class ScheduleService:
    """Keep persistent schedule state and its runtime projection consistent."""

    def __init__(
        self,
        repository: ScriptScheduleRepository,
        script_repository: ScriptRepository,
        node_repository: NodeRepository,
        scheduler: ScriptScheduler,
    ) -> None:
        self._repository = repository
        self._script_repository = script_repository
        self._node_repository = node_repository
        self._scheduler = scheduler

    async def create_or_update(
        self, script_id: UUID, data: ScheduleRequest
    ) -> ScheduledJob:
        """Validate, persist, and register a script schedule."""
        if await self._script_repository.get_by_id(script_id) is None:
            raise ScriptNotFoundError("Script not found")
        self._validate_trigger(data.cron, data.timezone)
        for node_id in data.node_ids:
            if await self._node_repository.get_by_id(node_id) is None:
                raise NodeNotFoundError(f"Node {node_id} not found")

        schedule = await self._repository.upsert(
            script_id,
            {
                "cron": data.cron,
                "timezone": data.timezone,
                "node_ids": [str(node_id) for node_id in data.node_ids],
                "params": data.params,
                "enabled": True,
                "misfire_grace_seconds": data.misfire_grace_seconds,
                "operational_state": "registered",
                "last_error_type": None,
            },
        )
        await self._repository.commit()
        try:
            self._scheduler.schedule_script(
                script_id,
                data.cron,
                data.node_ids,
                params=data.params,
                timezone=data.timezone,
                misfire_grace_seconds=data.misfire_grace_seconds,
                schedule_id=schedule.id,
            )
        except (RuntimeError, ValueError) as exc:
            SCHEDULER_REGISTRATION_FAILURES.inc()
            schedule.operational_state = "registration_failed"
            schedule.last_error_type = type(exc).__name__
            await self._repository.commit()
            raise SchedulePersistenceError(
                "Schedule was saved but runtime registration failed"
            ) from exc
        return self._to_schema(schedule)

    async def get(self, script_id: UUID) -> ScheduledJob:
        """Return a persistent schedule."""
        schedule = await self._repository.get_by_script_id(script_id)
        if schedule is None:
            raise ScheduleNotFoundError("No schedule found for script")
        return self._to_schema(schedule)

    async def delete(self, script_id: UUID) -> None:
        """Delete persistent state and remove its runtime projection."""
        if not await self._repository.delete_by_script_id(script_id):
            raise ScheduleNotFoundError("No schedule found for script")
        self._scheduler.unschedule_script(script_id)

    async def mark_started(self, script_id: UUID) -> None:
        """Persist the beginning of one scheduled execution."""
        schedule = await self._repository.get_by_script_id(script_id)
        if schedule is not None:
            schedule.last_run_at = datetime.now(UTC)
            await self._repository.commit()

    async def mark_succeeded(self, script_id: UUID) -> None:
        """Persist a successful scheduled execution."""
        schedule = await self._repository.get_by_script_id(script_id)
        if schedule is not None:
            schedule.last_success_at = datetime.now(UTC)
            schedule.last_error_type = None
            await self._repository.commit()

    async def mark_failed(self, script_id: UUID, error_type: str) -> None:
        """Persist a safe scheduled execution failure."""
        schedule = await self._repository.get_by_script_id(script_id)
        if schedule is not None:
            schedule.last_failure_at = datetime.now(UTC)
            schedule.last_error_type = error_type
            await self._repository.commit()

    async def restore(self) -> tuple[int, int]:
        """Rebuild the in-memory runtime projection from PostgreSQL state."""
        restored = 0
        failed = 0
        schedules = await self._repository.list_enabled()
        SCHEDULER_ACTIVE.set(len(schedules))
        persistent_ids = {str(schedule.script_id) for schedule in schedules}
        for runtime in self._scheduler.list_schedules():
            if runtime["job_id"] not in persistent_ids:
                self._scheduler.unschedule_script(UUID(runtime["job_id"]))
        for schedule in schedules:
            try:
                node_ids = [UUID(value) for value in schedule.node_ids]
                self._scheduler.schedule_script(
                    schedule.script_id,
                    schedule.cron,
                    node_ids,
                    params=schedule.params,
                    timezone=schedule.timezone,
                    misfire_grace_seconds=schedule.misfire_grace_seconds,
                    schedule_id=schedule.id,
                )
                schedule.operational_state = "registered"
                schedule.last_error_type = None
                schedule.next_run_at = self._scheduler.get_next_run_time(
                    schedule.script_id
                )
                restored += 1
                SCHEDULER_RESTORED.inc()
            except (RuntimeError, ValueError, ZoneInfoNotFoundError) as exc:
                SCHEDULER_REGISTRATION_FAILURES.inc()
                schedule.operational_state = "registration_failed"
                schedule.last_error_type = type(exc).__name__
                failed += 1
        await self._repository.commit()
        return restored, failed

    @staticmethod
    def _validate_trigger(cron: str, timezone: str) -> None:
        try:
            zone = ZoneInfo(timezone)
            CronTrigger.from_crontab(cron, timezone=zone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ScheduleValidationError(
                "Invalid cron expression or timezone"
            ) from exc

    @staticmethod
    def _to_schema(schedule: object) -> ScheduledJob:
        return ScheduledJob.model_validate(schedule, from_attributes=True)
