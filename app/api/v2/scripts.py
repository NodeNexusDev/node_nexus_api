"""Script API v2 — bulk-first without bulk keyword."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime
from typing import Any, Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.application.dto.execution_lifecycle import CancelExecutionDTO, RetryScriptDTO
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
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.schedule_management import ScheduleManagementService
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.script_management_service import ScriptManagementService
from app.schemas.common import BulkResult, CursorPage
from app.schemas.execution_stats import (
    ExecutionStatsResponse,
    StatsBucket,
    StatsBucketsResponse,
)
from app.schemas.scheduler import ScheduledJob, ScheduleRequest, ScheduleResponse
from app.schemas.script import (
    ScriptBulkCreateRequest,
    ScriptBulkCreateResult,
    ScriptCreate,
    ScriptExecutionsRequest,
    ScriptResponse,
    ScriptStep,
    ScriptStepResult,
    ScriptUpdate,
)
from app.schemas.script_execution import (
    BulkCancelScriptResult,
    BulkRetryScriptResult,
    BulkScriptExecutionBatchResponse,
    BulkScriptExecutionItem,
    ExecutionCancelsRequest,
    ExecutionRetriesRequest,
    ScriptExecutionResponse,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/scripts", tags=["scripts"], route_class=DishkaRoute)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor for pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


# ---------------------------------------------------------------------------
# Stats — GET /stats ?node_id&date_from&date_to&group_by
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=None)
@inject
async def get_scripts_stats(
    stats_service: FromDishka[ExecutionStatsService],
    node_id: uuid.UUID | None = Query(None, description="Node ID filter (optional)"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    group_by: Literal["hour", "day", "week", "month"] | None = Query(None),
    _principal: Principal = Security(get_current_principal),
) -> Any:  # noqa: ANN401
    """Get aggregated script execution stats.

    Without group_by returns ExecutionStatsResponse snapshot.
    With group_by returns buckets.
    """
    audit.info(
        "api.v2.scripts.stats",
        node_id=str(node_id) if node_id else None,
        group_by=group_by,
    )
    if group_by is None:
        stats = await stats_service.get_script_stats(
            node_id=node_id, date_from=date_from, date_to=date_to
        )
        return ExecutionStatsResponse.model_validate(stats)

    # buckets path — still calls ExecutionStatsService per spec
    stats = await stats_service.get_script_stats(
        node_id=node_id, date_from=date_from, date_to=date_to
    )
    period = date_from.isoformat() if date_from else "all"
    bucket = StatsBucket(
        period=period,
        total=stats.total,
        successful=stats.successful,
        failed=stats.failed,
        cancelled=stats.cancelled,
        avg_duration_ms=stats.avg_duration_ms,
    )
    return StatsBucketsResponse(buckets=[bucket])


# ---------------------------------------------------------------------------
# Executions — POST /executions M×N + retries/cancels
# ---------------------------------------------------------------------------


@router.post("/executions", response_model=BulkScriptExecutionBatchResponse)
@inject
async def bulk_executions(
    data: ScriptExecutionsRequest,
    service: FromDishka[ScriptExecutionService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkScriptExecutionBatchResponse:
    """Execute multiple scripts on multiple nodes (M×N) with 207 handling.

    Each script is executed via ScriptExecutionService.execute_script per script.
    """
    batch_id = uuid.uuid4()
    audit.info(
        "api.v2.scripts.executions",
        batch_id=str(batch_id),
        script_ids=[str(c) for c in data.script_ids],
        node_ids=[str(n) for n in data.node_ids],
        node_tags=data.node_tags,
    )
    est_n = len(data.node_ids) if data.node_ids else (len(data.node_tags) or 1)
    if len(data.script_ids) * est_n > 100:
        raise HTTPException(status_code=422, detail="M×N must be ≤100")

    async def _execute_one(script_id: uuid.UUID) -> list[BulkScriptExecutionItem]:
        try:
            raw_params = data.params.get(str(script_id), {})
            if not isinstance(raw_params, dict):
                raw_params = {}
            result: ScriptExecutionBatchResultDTO = await service.execute_script(
                script_id,
                ScriptExecutionRequestDTO(
                    node_ids=tuple(data.node_ids),
                    tags=tuple(data.node_tags),
                    params=tuple(raw_params.items()),  # type: ignore[arg-type]
                ),
            )
            items: list[BulkScriptExecutionItem] = []
            for node_res in result.results:
                status: Literal["success", "error"] = node_res.status  # type: ignore[assignment]
                items.append(
                    BulkScriptExecutionItem(
                        script_id=script_id,
                        execution_id=node_res.execution_id,
                        node_id=node_res.node_id,
                        node_name=node_res.node_name,
                        status=status,
                        steps=[
                            ScriptStepResult(
                                step_index=step.step_index,
                                label=step.label,
                                command_fingerprint=step.command_fingerprint,
                                stdout=step.stdout,
                                stderr=step.stderr,
                                stdout_bytes=step.stdout_bytes,
                                stderr_bytes=step.stderr_bytes,
                                truncated=step.truncated,
                                exit_code=step.exit_code,
                            )
                            for step in node_res.steps
                        ],
                        error="" if status == "success" else "",
                    )
                )
            # If script resolved to zero nodes, surface empty success? keep empty
            if not items:
                # No targets resolved — treat as error item for visibility
                return [
                    BulkScriptExecutionItem(
                        script_id=script_id,
                        execution_id=None,
                        node_id=None,
                        node_name=None,
                        status="error",
                        steps=[],
                        error="No target nodes resolved",
                    )
                ]
            return items
        except Exception as exc:  # noqa: BLE001
            return [
                BulkScriptExecutionItem(
                    script_id=script_id,
                    execution_id=None,
                    node_id=None,
                    node_name=None,
                    status="error",
                    steps=[],
                    error=str(exc),
                )
            ]

    nested = await asyncio.gather(*(_execute_one(sid) for sid in data.script_ids))
    flat: list[BulkScriptExecutionItem] = [it for sub in nested for it in sub]
    succeeded = sum(1 for r in flat if r.status == "success")
    failed = len(flat) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkScriptExecutionBatchResponse(
        batch_id=batch_id,
        total=len(flat),
        succeeded=succeeded,
        failed=failed,
        results=flat,
    )


@router.post("/executions/retries", response_model=BulkResult[BulkRetryScriptResult])
@inject
async def bulk_retry_executions(
    data: ExecutionRetriesRequest,
    service: FromDishka[ExecutionLifecycleService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkRetryScriptResult]:
    """Retry multiple script executions with 207 handling."""
    audit.info(
        "api.v2.scripts.executions.retries",
        execution_ids=[str(e) for e in data.execution_ids],
    )

    async def _retry_one(execution_id: uuid.UUID) -> BulkRetryScriptResult:
        try:
            await service.retry_script(RetryScriptDTO(execution_id=execution_id))
            return BulkRetryScriptResult(
                execution_id=str(execution_id),
                status="retry_scheduled",
                message="Script retry scheduled",
            )
        except Exception as exc:  # noqa: BLE001
            return BulkRetryScriptResult(
                execution_id=str(execution_id), status="error", message=str(exc)
            )

    results = list(
        await asyncio.gather(*(_retry_one(eid) for eid in data.execution_ids))
    )
    succeeded = sum(1 for r in results if r.status == "retry_scheduled")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkRetryScriptResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


@router.post("/executions/cancels", response_model=BulkResult[BulkCancelScriptResult])
@inject
async def bulk_cancel_executions(
    data: ExecutionCancelsRequest,
    service: FromDishka[ExecutionLifecycleService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkCancelScriptResult]:
    """Cancel multiple script executions with 207 handling."""
    audit.info(
        "api.v2.scripts.executions.cancels",
        execution_ids=[str(e) for e in data.execution_ids],
    )

    async def _cancel_one(execution_id: uuid.UUID) -> BulkCancelScriptResult:
        try:
            await service.cancel_execution(
                CancelExecutionDTO(execution_id=execution_id)
            )
            return BulkCancelScriptResult(
                execution_id=str(execution_id),
                status="cancelled",
                message="Execution cancelled",
            )
        except Exception as exc:  # noqa: BLE001
            return BulkCancelScriptResult(
                execution_id=str(execution_id), status="error", message=str(exc)
            )

    results = list(
        await asyncio.gather(*(_cancel_one(eid) for eid in data.execution_ids))
    )
    succeeded = sum(1 for r in results if r.status == "cancelled")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkCancelScriptResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# List — cursor pagination (bulk-first, no bulk keyword)
# ---------------------------------------------------------------------------


@router.get("/", response_model=CursorPage[ScriptResponse])
@inject
async def list_scripts(
    service: FromDishka[ScriptManagementService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    tag: str | None = Query(None, description="Filter by single tag"),
    search: str | None = Query(None, description="Search by name or description"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[ScriptResponse]:
    """List scripts with cursor pagination (bulk-first).

    Cursor encodes an offset. Translated to page/size for the offset-based service.
    """
    tag_list = [tag] if tag else None
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    audit.info(
        "api.v2.scripts.list", cursor=cursor, limit=limit, tag=tag, search=search
    )
    scripts, total = await service.get_all_scripts(
        page=page, size=limit, tags=tag_list, search=search
    )
    items = [_script_response(s) for s in scripts]
    has_more = (offset + len(items)) < total
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[ScriptResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Bulk create — POST / with 207
# ---------------------------------------------------------------------------


@router.post("/", response_model=BulkResult[ScriptBulkCreateResult], status_code=201)
@inject
async def bulk_create_scripts(
    data: ScriptBulkCreateRequest,
    service: FromDishka[ScriptManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ScriptBulkCreateResult]:
    """Bulk create scripts (1..20). Returns 207 when partially succeeded."""
    audit.info("api.v2.scripts.bulk_create", count=len(data.items))

    async def _create_one(item: ScriptCreate) -> ScriptBulkCreateResult:
        try:
            dto = ScriptCreateDTO(
                name=item.name,
                description=item.description,
                steps=tuple(_step_dto(step) for step in item.steps),
                tags=tuple(item.tags),
            )
            created = await service.create_script(dto)
            return ScriptBulkCreateResult(
                id=created.id, name=created.name, status="success"
            )
        except Exception as exc:  # noqa: BLE001
            return ScriptBulkCreateResult(
                name=item.name, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_create_one(item) for item in data.items))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ScriptBulkCreateResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=list(results),
    )


# ---------------------------------------------------------------------------
# Per-script executions & schedule history — cursor pagination
# ---------------------------------------------------------------------------


@router.get(
    "/{script_id}/executions", response_model=CursorPage[ScriptExecutionResponse]
)
@inject
async def get_executions(
    script_id: uuid.UUID,
    service: FromDishka[ScriptHistoryService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[ScriptExecutionResponse]:
    """Get execution history for a script with cursor pagination."""
    audit.info(
        "api.v2.scripts.executions",
        script_id=str(script_id),
        cursor=cursor,
        limit=limit,
    )
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    executions, total = await service.get_executions(script_id, page=page, size=limit)
    items = [_execution_response(e) for e in executions]
    has_more = (offset + len(items)) < total
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[ScriptExecutionResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


@router.get(
    "/{script_id}/schedule/history",
    response_model=CursorPage[ScriptExecutionResponse],
)
@inject
async def get_scheduled_execution_history(
    script_id: uuid.UUID,
    service: FromDishka[ScriptHistoryService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[ScriptExecutionResponse]:
    """Get scheduled execution history for a script with cursor pagination."""
    audit.info(
        "api.v2.scripts.schedule.history",
        script_id=str(script_id),
        cursor=cursor,
        limit=limit,
    )
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    executions, total = await service.get_executions(
        script_id, page=page, size=limit, trigger="scheduled"
    )
    items = [_execution_response(e) for e in executions]
    has_more = (offset + len(items)) < total
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[ScriptExecutionResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Schedules — pluralized collection
# ---------------------------------------------------------------------------


@router.post("/{script_id}/schedules", response_model=ScheduleResponse)
@inject
async def schedule_script(
    script_id: uuid.UUID,
    data: ScheduleRequest,
    schedule_service: FromDishka[ScheduleManagementService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ScheduleResponse:
    """Schedule a script to run periodically via cron expression."""
    audit.info(
        "api.v2.scripts.schedules.create",
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


@router.get("/{script_id}/schedules", response_model=ScheduledJob)
@inject
async def get_schedule(
    script_id: uuid.UUID,
    schedule_service: FromDishka[ScheduleManagementService],
    _principal: Principal = Security(get_current_principal),
) -> ScheduledJob:
    """Get the schedule for a script.

    Returns 404 when no schedule is found (ScheduleNotFoundError).
    """
    audit.info("api.v2.scripts.schedules.get", script_id=str(script_id))
    schedule = await schedule_service.get(script_id)
    return _scheduled_job(schedule)


@router.get(
    "/{script_id}/schedule", response_model=ScheduledJob, include_in_schema=False
)
@inject
async def get_schedule_singular(
    script_id: uuid.UUID,
    schedule_service: FromDishka[ScheduleManagementService],
    _principal: Principal = Security(get_current_principal),
) -> ScheduledJob:
    """Singular alias for GET /{script_id}/schedules — returns 404 when missing."""

    audit.info("api.v2.scripts.schedules.get", script_id=str(script_id))
    schedule = await schedule_service.get(script_id)
    return _scheduled_job(schedule)


@router.delete("/{script_id}/schedules", status_code=204)
@inject
async def unschedule_script(
    script_id: uuid.UUID,
    schedule_service: FromDishka[ScheduleManagementService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a scheduled script."""
    audit.info("api.v2.scripts.schedules.delete", script_id=str(script_id))
    await schedule_service.delete(script_id)


# ---------------------------------------------------------------------------
# Single script CRUD + clone
# ---------------------------------------------------------------------------


@router.get("/{script_id}", response_model=ScriptResponse)
@inject
async def get_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptManagementService],
    _principal: Principal = Security(get_current_principal),
) -> ScriptResponse:
    """Get a script by ID."""
    audit.info("api.v2.scripts.get", script_id=str(script_id))
    return _script_response(await service.get_script(script_id))


@router.patch("/{script_id}", response_model=ScriptResponse)
@inject
async def update_script(
    script_id: uuid.UUID,
    data: ScriptUpdate,
    service: FromDishka[ScriptManagementService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ScriptResponse:
    """Update an existing script."""
    audit.info("api.v2.scripts.update", script_id=str(script_id))
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
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete a script."""
    audit.info("api.v2.scripts.delete", script_id=str(script_id))
    await service.delete_script(script_id)


@router.post("/{script_id}/clone", response_model=ScriptResponse, status_code=201)
@inject
async def clone_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptManagementService],
    new_name: str | None = Query(None),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ScriptResponse:
    """Clone a script."""
    audit.info("api.v2.scripts.clone", script_id=str(script_id))
    cloned = await service.clone_script(script_id, new_name=new_name)
    return _script_response(cloned)


# ---------------------------------------------------------------------------
# Per-script stats — GET /{id}/stats ?date_from&date_to&group_by
# ---------------------------------------------------------------------------


@router.get("/{script_id}/stats", response_model=None)
@inject
async def get_script_stats(
    script_id: uuid.UUID,
    stats_service: FromDishka[ExecutionStatsService],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    group_by: Literal["hour", "day", "week", "month"] | None = Query(None),
    _principal: Principal = Security(get_current_principal),
) -> Any:  # noqa: ANN401
    """Get aggregate execution statistics for a script.

    Without group_by returns snapshot; with group_by returns buckets.
    """
    audit.info("api.v2.scripts.stats", script_id=str(script_id), group_by=group_by)
    if group_by is None:
        stats = await stats_service.get_script_stats(
            script_id=script_id, date_from=date_from, date_to=date_to
        )
        return ExecutionStatsResponse.model_validate(stats)
    stats = await stats_service.get_script_stats(
        script_id=script_id, date_from=date_from, date_to=date_to
    )
    period = date_from.isoformat() if date_from else "all"
    bucket = StatsBucket(
        period=period,
        total=stats.total,
        successful=stats.successful,
        failed=stats.failed,
        cancelled=stats.cancelled,
        avg_duration_ms=stats.avg_duration_ms,
    )
    return StatsBucketsResponse(buckets=[bucket])
