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
