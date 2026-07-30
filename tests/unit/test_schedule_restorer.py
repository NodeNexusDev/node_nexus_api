"""Tests for the schedule restoration application job."""

from unittest.mock import AsyncMock, MagicMock

from app.application.dto.schedule import ScheduleReconciliationResultDTO
from app.application.services.schedule_restorer import ScheduleRestorer


async def test_restorer_reconciles_and_publishes_readiness() -> None:
    reconciler = AsyncMock()
    scheduler = MagicMock()
    result = ScheduleReconciliationResultDTO(restored=3, failed=1)
    reconciler.reconcile.return_value = result

    restored = await ScheduleRestorer(reconciler, scheduler).run()

    assert restored == result
    scheduler.mark_restored.assert_called_once_with(failed=1)


def test_restorer_marks_disabled_scheduler_ready() -> None:
    scheduler = MagicMock()

    ScheduleRestorer(AsyncMock(), scheduler).mark_disabled()

    scheduler.mark_restored.assert_called_once_with(failed=0)
