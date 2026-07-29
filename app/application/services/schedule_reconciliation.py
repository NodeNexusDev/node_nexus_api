"""Application use case for reconciling persistent and runtime schedules."""

from app.application.dto.schedule import (
    RuntimeScheduleDTO,
    ScheduleReconciliationResultDTO,
    ScheduleViewDTO,
)
from app.application.ports.schedule import (
    JobSchedulerPort,
    ScheduleReader,
    ScheduleWriter,
)


class ScheduleReconciliationService:
    """Repair the ephemeral runtime projection from persistent desired state."""

    def __init__(
        self,
        reader: ScheduleReader,
        writer: ScheduleWriter,
        scheduler: JobSchedulerPort,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._scheduler = scheduler

    async def reconcile(self) -> ScheduleReconciliationResultDTO:
        schedules = await self._reader.list_enabled_schedules()
        desired_script_ids = {schedule.script_id for schedule in schedules}
        for runtime in self._scheduler.inspect():
            if runtime.script_id not in desired_script_ids:
                self._scheduler.remove(runtime.script_id)

        restored = 0
        failed = 0
        for schedule in schedules:
            try:
                runtime = self._scheduler.add_or_replace(self._to_runtime(schedule))
            except (RuntimeError, ValueError) as exc:
                await self._writer.mark_registration(
                    schedule.script_id,
                    state="registration_failed",
                    error_type=type(exc).__name__,
                )
                failed += 1
            else:
                await self._writer.mark_registration(
                    schedule.script_id,
                    state="registered",
                    error_type=None,
                    next_run_at=runtime.next_run_at,
                )
                restored += 1
        return ScheduleReconciliationResultDTO(restored=restored, failed=failed)

    @staticmethod
    def _to_runtime(schedule: ScheduleViewDTO) -> RuntimeScheduleDTO:
        return RuntimeScheduleDTO(
            schedule_id=schedule.id,
            script_id=schedule.script_id,
            cron=schedule.cron,
            timezone=schedule.timezone,
            node_ids=schedule.node_ids,
            params=schedule.params,
            misfire_grace_seconds=schedule.misfire_grace_seconds,
        )
