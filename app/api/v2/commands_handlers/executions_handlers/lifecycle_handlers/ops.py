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

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
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
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

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


def _command_response(command: CommandViewDTO) -> CommandResponse:
    return CommandResponse(
        id=command.id,
        name=command.name,
        description=command.description,
        command=command.command,
        parameters=[
            CommandParameter(
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


@router.post("/executions/retries", response_model=BulkResult[BulkRetryCommandResult])
@inject
async def bulk_retry_executions(
    data: ExecutionRetriesRequest,
    service: FromDishka[ExecutionLifecycleService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkRetryCommandResult]:
    """Retry multiple executions with 207 handling."""
    audit.info(
        "api.v2.commands.executions.retries",
        execution_ids=[str(e) for e in data.execution_ids],
    )  # noqa: E501

    async def _retry_one(execution_id: uuid.UUID) -> BulkRetryCommandResult:
        try:
            await service.retry_command(RetryCommandDTO(execution_id=execution_id))
            return BulkRetryCommandResult(
                execution_id=str(execution_id), status="retry_scheduled"
            )
        except Exception as exc:  # noqa: BLE001
            return BulkRetryCommandResult(
                execution_id=str(execution_id), status="error", message=str(exc)
            )

    results = list(
        await asyncio.gather(*(_retry_one(eid) for eid in data.execution_ids))
    )  # noqa: E501
    succeeded = sum(1 for r in results if r.status == "retry_scheduled")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[BulkRetryCommandResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


@router.post("/executions/cancels", response_model=BulkResult[BulkCancelCommandResult])
@inject
async def bulk_cancel_executions(
    data: ExecutionCancelsRequest,
    service: FromDishka[ExecutionLifecycleService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkCancelCommandResult]:
    """Cancel multiple executions with 207 handling."""
    audit.info(
        "api.v2.commands.executions.cancels",
        execution_ids=[str(e) for e in data.execution_ids],
    )  # noqa: E501

    async def _cancel_one(execution_id: uuid.UUID) -> BulkCancelCommandResult:
        try:
            await service.cancel_execution(
                CancelExecutionDTO(execution_id=execution_id)
            )  # noqa: E501
            return BulkCancelCommandResult(
                execution_id=str(execution_id), status="cancelled"
            )  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            return BulkCancelCommandResult(
                execution_id=str(execution_id), status="error", message=str(exc)
            )

    results = list(
        await asyncio.gather(*(_cancel_one(eid) for eid in data.execution_ids))
    )  # noqa: E501
    succeeded = sum(1 for r in results if r.status == "cancelled")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[BulkCancelCommandResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Single command CRUD + clone
# ---------------------------------------------------------------------------
