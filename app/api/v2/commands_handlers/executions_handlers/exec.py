# ruff: noqa: F401, I001
"""Command API v2 — bulk-first without bulk keyword."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security

from app.core.constants import DEFAULT_TIMEOUT
from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.api.v2._shared import command_response, script_response
from app.api.pagination import decode_offset, encode_offset
from app.api.v2._bulk import set_bulk_status
from app.application.dto.command_execution import BulkCommandRequestDTO
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandParameterDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.application.dto.execution_lifecycle import CancelExecutionDTO, RetryCommandDTO
from app.application.services.command_management_service import CommandManagementService
from app.application.services.execution_history_service import ExecutionHistoryService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.core.template import render_command
from app.schemas.command import (
    BulkExecutionBatchResponse,
    BulkExecutionItem,
    CommandBulkCreateRequest,
    CommandBulkCreateResult,
    CommandCreate,
    CommandExecutionsRequest,
    CommandParameter,
    CommandResponse,
    CommandUpdate,
    ExecutionCancelsRequest,
    ExecutionRetriesRequest,
    RawExecutionsRequest,
)
from app.schemas.common import BulkResult, CursorPage
from app.schemas.execution_stats import (
    ExecutionStatsResponse,
    StatsBucket,
    StatsBucketsResponse,
)
from app.schemas.node import (
    BulkCancelCommandResult,
    BulkRetryCommandResult,
    CommandHistoryResponse,
)

audit = structlog.get_logger("audit")

# Compatibility aliases for tests importing private helpers

router = APIRouter(route_class=DishkaRoute)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parameter_dto(parameter: CommandParameter) -> CommandParameterDTO:
    return CommandParameterDTO(
        name=parameter.name,
        type=parameter.type,
        required=parameter.required,
        default=parameter.default,
        description=parameter.description,
    )


            for parameter in command.parameters
        ],
        tags=list(command.tags),
        timeout=command.timeout,
        created_at=command.created_at,
        updated_at=command.updated_at,
    )


# ---------------------------------------------------------------------------
# List — cursor pagination (translate cursor -> page)
# ---------------------------------------------------------------------------


@router.post("/executions", response_model=BulkExecutionBatchResponse)
@inject
async def bulk_executions(
    data: CommandExecutionsRequest,
    cmd_service: FromDishka[CommandManagementService],
    bulk_service: FromDishka[NodeBulkCommandService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkExecutionBatchResponse:
    """Execute multiple commands on multiple nodes (M×N) with 207 handling.

    Each command is rendered via render_command per params mapping,
    then executed via NodeBulkCommandService.execute across node_ids/node_tags.
    """
    batch_id = uuid.uuid4()
    audit.info(
        "api.v2.commands.executions",
        batch_id=str(batch_id),
        command_ids=[str(c) for c in data.command_ids],
        node_ids=[str(n) for n in data.node_ids],
        node_tags=data.node_tags,
    )
    # M*N guard (best-effort)
    est_n = len(data.node_ids) if data.node_ids else (len(data.node_tags) or 1)
    if len(data.command_ids) * est_n > 100:
        raise HTTPException(status_code=422, detail="M×N must be ≤100")

    async def _execute_one(command_id: uuid.UUID) -> list[BulkExecutionItem]:
        try:
            cmd = await cmd_service.get_command(command_id)
            raw_params = data.params.get(str(command_id), {})
            if not isinstance(raw_params, dict):
                raw_params = {}
            rendered = render_command(
                cmd.command,
                list(cmd.parameters),
                raw_params,
            )
            effective_timeout = (
                data.timeout if data.timeout is not None else cmd.timeout
            )
            result = await bulk_service.execute(
                BulkCommandRequestDTO(
                    command=rendered,
                    node_ids=tuple(data.node_ids),
                    tags=tuple(data.node_tags),
                    command_id=command_id,
                    timeout=effective_timeout,
                )
            )
            items: list[BulkExecutionItem] = []
            for node_res in result.results:
                status: Literal["success", "error"] = (
                    "success" if node_res.exit_code == 0 else "error"
                )
                items.append(
                    BulkExecutionItem(
                        command_id=command_id,
                        command=rendered,
                        node_id=node_res.node_id,
                        node_name=node_res.node_name,
                        stdout=node_res.stdout,
                        stderr=node_res.stderr,
                        exit_code=node_res.exit_code,
                        status=status,
                        error="" if status == "success" else node_res.stderr,
                    )
                )
            return items
        except Exception as exc:  # noqa: BLE001
            return [
                BulkExecutionItem(
                    command_id=command_id,
                    node_id=None,
                    node_name=None,
                    stdout="",
                    stderr=str(exc),
                    exit_code=None,
                    status="error",
                    error=str(exc),
                )
            ]

    nested = await asyncio.gather(*(_execute_one(cid) for cid in data.command_ids))
    flat: list[BulkExecutionItem] = [it for sub in nested for it in sub]
    succeeded = sum(1 for r in flat if r.status == "success")
    failed = len(flat) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkExecutionBatchResponse(
        batch_id=batch_id,
        total=len(flat),
        succeeded=succeeded,
        failed=failed,
        results=flat,
    )


@router.post("/raw-executions", response_model=BulkExecutionBatchResponse)
@inject
async def bulk_raw_executions(
    data: RawExecutionsRequest,
    bulk_service: FromDishka[NodeBulkCommandService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkExecutionBatchResponse:
    """Execute raw command strings on multiple nodes (M×N) with 207."""
    batch_id = uuid.uuid4()
    audit.info(
        "api.v2.commands.raw_executions",
        batch_id=str(batch_id),
        commands_count=len(data.commands),
        node_ids=[str(n) for n in data.node_ids],
        node_tags=data.node_tags,
    )
    est_n = len(data.node_ids) if data.node_ids else (len(data.node_tags) or 1)
    if len(data.commands) * est_n > 100:
        raise HTTPException(status_code=422, detail="M×N must be ≤100")

    async def _execute_raw(command: str) -> list[BulkExecutionItem]:
        try:
            effective_timeout = data.timeout if data.timeout is not None else DEFAULT_TIMEOUT
            result = await bulk_service.execute(
                BulkCommandRequestDTO(
                    command=command,
                    node_ids=tuple(data.node_ids),
                    tags=tuple(data.node_tags),
                    timeout=effective_timeout,
                )
            )
            items: list[BulkExecutionItem] = []
            for node_res in result.results:
                status: Literal["success", "error"] = (
                    "success" if node_res.exit_code == 0 else "error"
                )
                items.append(
                    BulkExecutionItem(
                        command=command,
                        node_id=node_res.node_id,
                        node_name=node_res.node_name,
                        stdout=node_res.stdout,
                        stderr=node_res.stderr,
                        exit_code=node_res.exit_code,
                        status=status,
                        error="" if status == "success" else node_res.stderr,
                    )
                )
            return items
        except Exception as exc:  # noqa: BLE001
            return [
                BulkExecutionItem(
                    command=command,
                    node_id=None,
                    node_name=None,
                    stdout="",
                    stderr=str(exc),
                    exit_code=None,
                    status="error",
                    error=str(exc),
                )
            ]

    nested = await asyncio.gather(*(_execute_raw(cmd) for cmd in data.commands))
    flat: list[BulkExecutionItem] = [it for sub in nested for it in sub]
    succeeded = sum(1 for r in flat if r.status == "success")
    failed = len(flat) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkExecutionBatchResponse(
        batch_id=batch_id,
        total=len(flat),
        succeeded=succeeded,
        failed=failed,
        results=flat,
    )


# ---------------------------------------------------------------------------
# Executions history — GET /executions/history ?batch_id&cursor&limit
# ---------------------------------------------------------------------------
