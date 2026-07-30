"""APScheduler-backed runtime job adapter."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime
from app.application.dto.schedule import RuntimeJobViewDTO, RuntimeScheduleDTO


class ApschedulerJobScheduler:
    """Expose the concrete scheduler through the application runtime port."""

    def __init__(self, scheduler: ApschedulerRuntime) -> None:
        self._scheduler = scheduler

    def is_ready(self) -> bool:
        return self._scheduler.ready

    def owns_execution(self) -> bool:
        return self._scheduler.owns_execution

    def mark_restored(self, *, failed: int) -> None:
        self._scheduler.mark_restored(failed=failed)

    def validate(self, cron: str, timezone: str) -> None:
        CronTrigger.from_crontab(cron, timezone=ZoneInfo(timezone))

    def add_or_replace(self, schedule: RuntimeScheduleDTO) -> RuntimeJobViewDTO:
        self._scheduler.schedule_script(
            schedule.script_id,
            schedule.cron,
            list(schedule.node_ids),
            params=dict(schedule.params),
            timezone=schedule.timezone,
            misfire_grace_seconds=schedule.misfire_grace_seconds,
            schedule_id=schedule.schedule_id,
        )
        return RuntimeJobViewDTO(
            script_id=schedule.script_id,
            next_run_at=self._scheduler.get_next_run_time(schedule.script_id),
        )

    def remove(self, script_id: UUID) -> bool:
        return self._scheduler.unschedule_script(script_id)

    def inspect(self) -> list[RuntimeJobViewDTO]:
        return [
            RuntimeJobViewDTO(
                script_id=UUID(job["job_id"]),
                next_run_at=self._parse_datetime(job.get("next_run_time")),
            )
            for job in self._scheduler.list_schedules()
        ]

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return None
