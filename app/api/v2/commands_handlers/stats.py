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
        created_at=command.created_at,
        updated_at=command.updated_at,
    )


# ---------------------------------------------------------------------------
# List — cursor pagination (translate cursor -> page)
# ---------------------------------------------------------------------------


@router.get("/stats")
@inject
async def get_commands_stats(
    stats_service: FromDishka[ExecutionStatsService],
    node_id: uuid.UUID | None = Query(None, description="Node ID filter (optional)"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    group_by: Literal["hour", "day", "week", "month"] | None = Query(None),
    _principal: Principal = Security(get_current_principal),
) -> Any:  # noqa: ANN401
    """Get aggregated command execution stats.

    Without group_by returns ExecutionStatsResponse snapshot.
    With group_by returns buckets.
    """
    audit.info(
        "api.v2.commands.stats",
        node_id=str(node_id) if node_id else None,
        group_by=group_by,
    )
    if group_by is None:
        if node_id is not None:
            stats = await stats_service.get_node_command_stats(
                node_id=node_id, date_from=date_from, date_to=date_to
            )
        else:
            stats = await stats_service.get_command_stats(
                node_id=node_id, date_from=date_from, date_to=date_to
            )
        return ExecutionStatsResponse.model_validate(stats)

    # buckets path — still calls ExecutionStatsService per spec
    if node_id is not None:
        stats = await stats_service.get_node_command_stats(
            node_id=node_id, date_from=date_from, date_to=date_to
        )
    else:
        stats = await stats_service.get_command_stats(
            node_id=node_id, date_from=date_from, date_to=date_to
        )
    # Build single bucket from snapshot as placeholder; real bucketing would be
    # delegated to DashboardMetricsService but spec mandates ExecutionStatsService
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
# Executions — POST /executions M×N + POST /raw-executions
# ---------------------------------------------------------------------------


@router.get("/{command_id}/stats")
@inject
async def get_command_stats(
    command_id: uuid.UUID,
    stats_service: FromDishka[ExecutionStatsService],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    group_by: Literal["hour", "day", "week", "month"] | None = Query(None),
    _principal: Principal = Security(get_current_principal),
) -> Any:  # noqa: ANN401
    """Get aggregate execution statistics for a command.

    Without group_by returns snapshot; with group_by returns buckets.
    """
    audit.info("api.v2.commands.stats", command_id=str(command_id), group_by=group_by)
    if group_by is None:
        stats = await stats_service.get_command_stats(
            command_id=command_id, date_from=date_from, date_to=date_to
        )
        return ExecutionStatsResponse.model_validate(stats)
    stats = await stats_service.get_command_stats(
        command_id=command_id, date_from=date_from, date_to=date_to
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
