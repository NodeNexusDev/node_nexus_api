# ruff: noqa: F401, I001
"""Script API v2 — bulk-first without bulk keyword."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security

from app.core.constants import DEFAULT_TIMEOUT
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
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    # Handle non-aligned offset correctly (offset % limit != 0)
    remainder = offset % limit if limit else 0
    page = offset // limit + 1 if limit else 1
    fetch_size = limit + remainder if remainder else limit
    audit.info(
        "api.v2.scripts.list", cursor=cursor, limit=limit, tag=tag, search=search
    )
    scripts, total = await service.get_all_scripts(
        page=page, size=fetch_size, tags=tag_list, search=search
    )
    if remainder:
        scripts = scripts[remainder : remainder + limit]
    items = [_script_response(s) for s in scripts]
    has_more = (offset + len(items)) < total
    next_cursor = encode_offset(offset + limit) if has_more else None
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
                timeout=item.timeout if item.timeout is not None else DEFAULT_TIMEOUT,
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
