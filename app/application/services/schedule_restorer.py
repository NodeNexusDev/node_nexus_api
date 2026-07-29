"""Application job for restoring persistent schedules into runtime."""

from app.application.dto.schedule import ScheduleReconciliationResultDTO
from app.application.ports.schedule import JobSchedulerPort
from app.application.services.schedule_reconciliation import (
    ScheduleReconciliationService,
)


class ScheduleRestorer:
    """Reconcile schedules and publish runtime readiness."""

    def __init__(
        self,
        reconciler: ScheduleReconciliationService,
        scheduler: JobSchedulerPort,
    ) -> None:
        self._reconciler = reconciler
        self._scheduler = scheduler

    async def run(self) -> ScheduleReconciliationResultDTO:
        """Restore runtime jobs and publish the reconciliation outcome."""
        result = await self._reconciler.reconcile()
        self._scheduler.mark_restored(failed=result.failed)
        return result

    def mark_disabled(self) -> None:
        """Publish readiness when scheduling is intentionally disabled."""
        self._scheduler.mark_restored(failed=0)
