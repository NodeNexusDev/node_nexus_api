"""Script API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.schedule import ScheduleRequestDTO, ScheduleViewDTO
from app.application.dto.script_execution import (
    ScriptExecutionBatchResultDTO,
    ScriptExecutionDTO,
    ScriptExecutionRequestDTO,
)
from app.application.dto.script_management import (
    ScriptCreateDTO,
    ScriptStepDTO,
    ScriptUpdateDTO,
    ScriptViewDTO,
)
from app.application.services.schedule_management import (
    ScheduleManagementService,
)
from app.schemas.node import PaginatedResponse
from app.schemas.scheduler import ScheduledJob, ScheduleRequest, ScheduleResponse
from app.schemas.script import (
    ScriptCreate,
    ScriptExecuteRequest,
    ScriptExecutionBatchResult,
    ScriptResponse,
    ScriptStep,
    ScriptUpdate,
)
from app.schemas.script_execution import ScriptExecutionResponse
from app.services.script_execution_service import ScriptExecutionService
from app.services.script_history_service import ScriptHistoryService
from app.services.script_management_service import ScriptManagementService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/scripts", tags=["scripts"], route_class=DishkaRoute)


def _step_dto(step: ScriptStep) -> ScriptStepDTO:
    return ScriptStepDTO(
        label=step.label,
        type=step.type,
        command=step.command,
        command_id=step.command_id,
        params=tuple(step.params.items()),
        on_failure=step.on_failure,
    )


def _script_response(script: ScriptViewDTO) -> ScriptResponse:
    return ScriptResponse(
        id=script.id,
        name=script.name,
        description=script.description,
        steps=[
            {
                "label": step.label,
                "type": step.type,
                "command": step.command,
                "command_id": step.command_id,
                "params": dict(step.params),
                "on_failure": step.on_failure,
            }
            for step in script.steps
        ],
        tags=list(script.tags),
        created_at=script.created_at,
        updated_at=script.updated_at,
    )


def _execution_response(execution: ScriptExecutionDTO) -> ScriptExecutionResponse:
    return ScriptExecutionResponse(
        id=execution.id,
        script_id=execution.script_id,
        node_id=execution.node_id,
        params=dict(execution.params),
        status=execution.status,
        steps=[
            {
                "step_index": step.step_index,
                "label": step.label,
                "command_fingerprint": step.command_fingerprint,
                "stdout": step.stdout,
                "stderr": step.stderr,
                "stdout_bytes": step.stdout_bytes,
                "stderr_bytes": step.stderr_bytes,
                "truncated": step.truncated,
                "exit_code": step.exit_code,
            }
            for step in execution.steps
        ],
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )


def _scheduled_job(schedule: ScheduleViewDTO) -> ScheduledJob:
    return ScheduledJob(
        id=schedule.id,
        script_id=schedule.script_id,
        cron=schedule.cron,
        timezone=schedule.timezone,
        node_ids=list(schedule.node_ids),
        params=dict(schedule.params),
        enabled=schedule.enabled,
        misfire_grace_seconds=schedule.misfire_grace_seconds,
        operational_state=schedule.operational_state,
        last_error_type=schedule.last_error_type,
        last_run_at=schedule.last_run_at,
        last_success_at=schedule.last_success_at,
        last_failure_at=schedule.last_failure_at,
        next_run_at=schedule.next_run_at,
    )


def _execution_batch_response(
    result: ScriptExecutionBatchResultDTO,
) -> ScriptExecutionBatchResult:
    return ScriptExecutionBatchResult(
        script_id=result.script_id,
        results=[
            {
                "execution_id": node.execution_id,
                "node_id": node.node_id,
                "node_name": node.node_name,
                "status": node.status,
                "steps": [
                    {
                        "step_index": step.step_index,
                        "label": step.label,
                        "command_fingerprint": step.command_fingerprint,
                        "stdout": step.stdout,
                        "stderr": step.stderr,
                        "stdout_bytes": step.stdout_bytes,
                        "stderr_bytes": step.stderr_bytes,
                        "truncated": step.truncated,
                        "exit_code": step.exit_code,
                    }
                    for step in node.steps
                ],
            }
            for node in result.results
        ],
    )


@router.get("/", response_model=PaginatedResponse[ScriptResponse])
@inject
async def get_scripts(
    service: FromDishka[ScriptManagementService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None, description="Filter by tag (AND)"),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[ScriptResponse]:
    """Get all scripts with pagination."""
    tag_list = [t.strip() for t in tag.split(",")] if tag else None
    audit.info("api.scripts.list", page=page, size=size, tags=tag_list)
    scripts, total = await service.get_all_scripts(page=page, size=size, tags=tag_list)
    return PaginatedResponse(
        items=[_script_response(script) for script in scripts],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{script_id}", response_model=ScriptResponse)
@inject
async def get_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptManagementService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Get a script by ID."""
    audit.info("api.scripts.get", script_id=str(script_id))
    return _script_response(await service.get_script(script_id))


@router.post("/", response_model=ScriptResponse, status_code=201)
@inject
async def create_script(
    data: ScriptCreate,
    service: FromDishka[ScriptManagementService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Create a new script."""
    audit.info("api.scripts.create", name=data.name)
    result = await service.create_script(
        ScriptCreateDTO(
            name=data.name,
            description=data.description,
            steps=tuple(_step_dto(step) for step in data.steps),
            tags=tuple(data.tags),
        )
    )
    return _script_response(result)


@router.put("/{script_id}", response_model=ScriptResponse)
@inject
async def update_script(
    script_id: uuid.UUID,
    data: ScriptUpdate,
    service: FromDishka[ScriptManagementService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Update an existing script."""
    audit.info("api.scripts.update", script_id=str(script_id))
    changes = data.model_dump(exclude_unset=True)
    if isinstance(changes.get("steps"), list):
        changes["steps"] = tuple(_step_dto(step) for step in (data.steps or ()))
    if isinstance(changes.get("tags"), list):
        changes["tags"] = tuple(changes["tags"])
    result = await service.update_script(
        script_id,
        ScriptUpdateDTO(changes=tuple(changes.items())),
    )
    return _script_response(result)


@router.delete("/{script_id}", status_code=204)
@inject
async def delete_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptManagementService],
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
    service: FromDishka[ScriptExecutionService],
    _key: str = Security(get_current_api_key),
) -> ScriptExecutionBatchResult:
    """Execute a script on multiple nodes."""
    audit.info(
        "api.scripts.execute",
        script_id=str(script_id),
        node_count=len(data.node_ids),
    )
    result = await service.execute_script(
        script_id,
        ScriptExecutionRequestDTO(
            node_ids=tuple(data.node_ids),
            params=tuple(data.params.items()),
        ),
    )
    return _execution_batch_response(result)


@router.get("/{script_id}/executions")
@inject
async def get_executions(
    script_id: uuid.UUID,
    service: FromDishka[ScriptHistoryService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[ScriptExecutionResponse]:
    """Get execution history for a script."""
    audit.info("api.scripts.executions", script_id=str(script_id))
    executions, total = await service.get_executions(script_id, page=page, size=size)
    return PaginatedResponse(
        items=[_execution_response(execution) for execution in executions],
        total=total,
        page=page,
        size=size,
    )


# --- Schedule endpoints ---


@router.post("/{script_id}/schedule", response_model=ScheduleResponse)
@inject
async def schedule_script(
    script_id: uuid.UUID,
    data: ScheduleRequest,
    schedule_service: FromDishka[ScheduleManagementService],
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
    schedule = await schedule_service.create_or_update(
        script_id,
        ScheduleRequestDTO(
            cron=data.cron,
            node_ids=tuple(data.node_ids),
            params=tuple(data.params.items()),
            timezone=data.timezone,
            misfire_grace_seconds=data.misfire_grace_seconds,
        ),
    )
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
    schedule_service: FromDishka[ScheduleManagementService],
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
    schedule_service: FromDishka[ScheduleManagementService],
    _key: str = Security(require_write_scope),
) -> ScheduledJob | None:
    """Get the schedule for a script."""
    audit.info("api.scripts.get_schedule", script_id=str(script_id))
    return _scheduled_job(await schedule_service.get(script_id))
