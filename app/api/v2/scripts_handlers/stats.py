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
