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
from app.api.v2._shared import command_response, script_response
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
from app.api.v2._bulk import set_bulk_status
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
    ScriptBulkUpdateRequest,
    ScriptBulkUpdateResult,
    ScriptCreate,
    ScriptDeletionsRequest,
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
# Bulk update — PATCH /  (207 on partial)
# ---------------------------------------------------------------------------


@router.patch("/", response_model=BulkResult[ScriptBulkUpdateResult])
@inject
async def bulk_update_scripts(
    data: ScriptBulkUpdateRequest,
    service: FromDishka[ScriptManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ScriptBulkUpdateResult]:
    """Bulk update scripts via PATCH /."""
    audit.info("api.v2.scripts.bulk_update", count=len(data.updates))

    async def _update_one(item: Any) -> ScriptBulkUpdateResult:  # noqa: ANN401
        try:
            changes = item.changes.model_dump(exclude_unset=True)
            if isinstance(changes.get("steps"), list):
                changes["steps"] = tuple(
                    _step_dto(s) for s in (item.changes.steps or ())
                )
            if isinstance(changes.get("tags"), list):
                changes["tags"] = tuple(changes["tags"])
            await service.update_script(
                item.id, ScriptUpdateDTO(changes=tuple(changes.items()))
            )
            return ScriptBulkUpdateResult(script_id=item.id, status="success")
        except Exception as exc:  # noqa: BLE001
            return ScriptBulkUpdateResult(
                script_id=item.id, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_update_one(u) for u in data.updates))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[ScriptBulkUpdateResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/deletions", response_model=BulkResult[ScriptBulkUpdateResult])
@inject
async def bulk_delete_scripts(
    data: ScriptDeletionsRequest,
    service: FromDishka[ScriptManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ScriptBulkUpdateResult]:
    """Bulk delete scripts via POST /deletions (207 on partial)."""
    audit.info("api.v2.scripts.bulk_delete", count=len(data.ids))

    async def _delete_one(sid: uuid.UUID) -> ScriptBulkUpdateResult:
        try:
            await service.delete_script(sid)
            return ScriptBulkUpdateResult(script_id=sid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ScriptBulkUpdateResult(script_id=sid, status="error", error=str(exc))

    results = await asyncio.gather(*(_delete_one(sid) for sid in data.ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[ScriptBulkUpdateResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


# ---------------------------------------------------------------------------
# Stats — GET /stats ?node_id&date_from&date_to&group_by
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
    return script_response(await service.get_script(script_id))


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
    return script_response(result)


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
    return script_response(cloned)


# ---------------------------------------------------------------------------
# Per-script stats — GET /{id}/stats ?date_from&date_to&group_by
# ---------------------------------------------------------------------------
