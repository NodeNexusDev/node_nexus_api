"""Script API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.schemas.node import PaginatedResponse
from app.schemas.scheduler import ScheduledJob, ScheduleRequest, ScheduleResponse
from app.schemas.script import (
    ScriptCreate,
    ScriptExecuteRequest,
    ScriptExecutionBatchResult,
    ScriptResponse,
    ScriptUpdate,
)
from app.schemas.script_execution import ScriptExecutionResponse
from app.services.schedule_service import ScheduleService
from app.services.script_service import ScriptService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/scripts", tags=["scripts"], route_class=DishkaRoute)


@router.get("/", response_model=PaginatedResponse[ScriptResponse])
@inject
async def get_scripts(
    service: FromDishka[ScriptService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None, description="Filter by tag (AND)"),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[ScriptResponse]:
    """Get all scripts with pagination."""
    tag_list = [t.strip() for t in tag.split(",")] if tag else None
    audit.info("api.scripts.list", page=page, size=size, tags=tag_list)
    scripts, total = await service.get_all_scripts(page=page, size=size, tags=tag_list)
    return PaginatedResponse(items=scripts, total=total, page=page, size=size)


@router.get("/{script_id}", response_model=ScriptResponse)
@inject
async def get_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Get a script by ID."""
    audit.info("api.scripts.get", script_id=str(script_id))
    return await service.get_script(script_id)


@router.post("/", response_model=ScriptResponse, status_code=201)
@inject
async def create_script(
    data: ScriptCreate,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Create a new script."""
    audit.info("api.scripts.create", name=data.name)
    return await service.create_script(data)


@router.put("/{script_id}", response_model=ScriptResponse)
@inject
async def update_script(
    script_id: uuid.UUID,
    data: ScriptUpdate,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Update an existing script."""
    audit.info("api.scripts.update", script_id=str(script_id))
    return await service.update_script(script_id, data)


@router.delete("/{script_id}", status_code=204)
@inject
async def delete_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> None:
    """Delete a script."""
    audit.info("api.scripts.delete", script_id=str(script_id))
    await service.delete_script(script_id)


@router.post("/{script_id}/execute", response_model=ScriptExecutionBatchResult)
@inject
async def execute_script(
    script_id: uuid.UUID,
    data: ScriptExecuteRequest,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptExecutionBatchResult:
    """Execute a script on multiple nodes."""
    audit.info(
        "api.scripts.execute",
        script_id=str(script_id),
        node_count=len(data.node_ids),
    )
    return await service.execute_script(script_id, data)


@router.get("/{script_id}/executions")
@inject
async def get_executions(
    script_id: uuid.UUID,
    service: FromDishka[ScriptService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[ScriptExecutionResponse]:
    """Get execution history for a script."""
    audit.info("api.scripts.executions", script_id=str(script_id))
    executions, total = await service.get_executions(script_id, page=page, size=size)
    return PaginatedResponse(items=executions, total=total, page=page, size=size)


# --- Schedule endpoints ---


@router.post("/{script_id}/schedule", response_model=ScheduleResponse)
@inject
async def schedule_script(
    script_id: uuid.UUID,
    data: ScheduleRequest,
    schedule_service: FromDishka[ScheduleService],
    _key: str = Security(require_write_scope),
) -> ScheduleResponse:
    """Schedule a script to run periodically via cron expression.

    Requires a valid cron expression (e.g., '0 9 * * *' for daily at 9am).
    """
    audit.info(
        "api.scripts.schedule",
        script_id=str(script_id),
        cron=data.cron,
        node_ids=[str(n) for n in data.node_ids],
    )
    schedule = await schedule_service.create_or_update(script_id, data)
    return ScheduleResponse(
        script_id=str(script_id),
        cron=schedule.cron,
        timezone=schedule.timezone,
        message="Script scheduled successfully",
    )


@router.delete("/{script_id}/schedule", status_code=200)
@inject
async def unschedule_script(
    script_id: uuid.UUID,
    schedule_service: FromDishka[ScheduleService],
    _key: str = Security(require_write_scope),
) -> dict:
    """Remove a scheduled script."""
    audit.info("api.scripts.unschedule", script_id=str(script_id))
    await schedule_service.delete(script_id)
    return {"message": "Script unscheduled", "script_id": str(script_id)}


@router.get("/{script_id}/schedule", response_model=ScheduledJob | None)
@inject
async def get_schedule(
    script_id: uuid.UUID,
    schedule_service: FromDishka[ScheduleService],
    _key: str = Security(require_write_scope),
) -> ScheduledJob | None:
    """Get the schedule for a script."""
    audit.info("api.scripts.get_schedule", script_id=str(script_id))
    return await schedule_service.get(script_id)
