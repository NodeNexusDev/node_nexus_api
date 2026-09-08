# ruff: noqa: F401, I001
"""Script API v2 — bulk-first without bulk keyword."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.api.pagination import decode_offset, encode_offset
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

# Compatibility aliases for tests importing private helpers
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

router = APIRouter(route_class=DishkaRoute)


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
        timeout=script.timeout,
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


# ---------------------------------------------------------------------------
# Stats — GET /stats ?node_id&date_from&date_to&group_by
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

    return await _get_executions(service, script_id, cursor, limit)


@router.get(
    "/executions/history",
    response_model=CursorPage[ScriptExecutionResponse],
    include_in_schema=False,
)
@inject
async def get_executions_history_alias(
    script_id: Annotated[uuid.UUID, Query(description="Script ID to filter by")],
    service: FromDishka[ScriptHistoryService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[ScriptExecutionResponse]:
    """RESTful alias for GET /{id}/executions (bulk-first consistency)."""

    return await _get_executions(service, script_id, cursor, limit)


async def _get_executions(
    service: ScriptHistoryService,
    script_id: uuid.UUID,
    cursor: str | None,
    limit: int,
) -> CursorPage[ScriptExecutionResponse]:
    """Internal helper for per-script executions pagination."""
    audit.info(
        "api.v2.scripts.executions",
        script_id=str(script_id),
        cursor=cursor,
        limit=limit,
    )
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    remainder = offset % limit if limit else 0
    page = offset // limit + 1 if limit else 1
    fetch_size = limit + remainder if remainder else limit
    executions, total = await service.get_executions(
        script_id, page=page, size=fetch_size
    )
    items = [_execution_response(e) for e in executions]
    if remainder:
        items = items[remainder : remainder + limit]
    has_more = (offset + len(items)) < total
    next_cursor = encode_offset(offset + limit) if has_more else None
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
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    remainder = offset % limit if limit else 0
    page = offset // limit + 1 if limit else 1
    fetch_size = limit + remainder if remainder else limit
    executions, total = await service.get_executions(
        script_id, page=page, size=fetch_size, trigger="scheduled"
    )
    items = [_execution_response(e) for e in executions]
    if remainder:
        items = items[remainder : remainder + limit]
    has_more = (offset + len(items)) < total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return CursorPage[ScriptExecutionResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Schedules — pluralized collection
# ---------------------------------------------------------------------------
