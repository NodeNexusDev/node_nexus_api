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
