"""Internal E2E-only endpoints for test isolation."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Depends

from app.application.ports.audit_outbox_controller import AuditOutboxController
from app.api.deps import get_current_api_key

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
    _api_key: str = Depends(get_current_api_key),
) -> dict[str, str]:
    """Pause audit outbox worker for clean E2E DB truncation."""
    await audit_worker.stop()
    return {"status": "paused"}


@router.post("/resume-background")
@inject
async def resume_background_tasks(
    audit_worker: FromDishka[AuditOutboxController],
    _api_key: str = Depends(get_current_api_key),
) -> dict[str, str]:
    """Resume audit outbox worker after E2E DB truncation."""
    audit_worker.start()
    return {"status": "resumed"}
