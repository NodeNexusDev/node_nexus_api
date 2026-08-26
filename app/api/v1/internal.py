"""Internal E2E-only endpoints for test isolation."""

import uuid

from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status

from app.api.deps import Principal, get_current_principal
from app.application.ports.audit_outbox_controller import AuditOutboxController
from app.application.ports.schedule import JobSchedulerPort, ScheduleReader
from app.application.services.scheduled_script_executor import ScheduledScriptExecutor
from app.core.config import Settings

router = APIRouter(
    prefix="/internal/e2e",
    tags=["internal"],
    route_class=DishkaRoute,
    include_in_schema=False,
)


@router.post("/pause-background")
@inject
async def pause_background_tasks(
    audit_worker: FromDishka[AuditOutboxController],
    _api_key: Principal = Security(get_current_principal),
) -> dict[str, str]:
    """Pause audit outbox worker for clean E2E DB truncation."""
    await audit_worker.stop()
    return {"status": "paused"}


@router.post("/resume-background")
@inject
async def resume_background_tasks(
    audit_worker: FromDishka[AuditOutboxController],
    _api_key: Principal = Security(get_current_principal),
) -> dict[str, str]:
    """Resume audit outbox worker after E2E DB truncation."""
    audit_worker.start()
    return {"status": "resumed"}


@router.post("/scheduler/{script_id}/trigger-now")
@inject
async def trigger_scheduled_script_now(
    script_id: uuid.UUID,
    scheduler: FromDishka[JobSchedulerPort],
    schedule_reader: FromDishka[ScheduleReader],
    executor: FromDishka[ScheduledScriptExecutor],
    settings: FromDishka[Settings],
    _api_key: Principal = Security(get_current_principal),
) -> dict[str, str]:
    """Immediately execute a scheduled script for E2E verification.

    This bypasses the cron trigger and runs the scheduled executor directly,
    while still recording lifecycle metadata (started/succeeded/failed)
    through the same path used by the real scheduler.
    """
    if not settings.E2E_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="E2E endpoints are disabled",
        )
    if not scheduler.owns_execution:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler does not own execution",
        )

    schedule = await schedule_reader.get_schedule(script_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    params = dict(schedule.params)
    try:
        await executor.execute(
            script_id,
            list(schedule.node_ids),
            params,
            schedule_id=schedule.id,
        )
    except Exception:
        # The executor records the failed execution itself; we only need to
        # signal that the trigger was processed so E2E tests can poll history.
        return {"status": "failed"}
    return {"status": "triggered"}
