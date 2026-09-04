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


@router.get("/history", response_model=CursorPage[CommandHistoryResponse])
@inject
async def get_command_history(
    service: FromDishka[ExecutionHistoryService],
    node_id: Annotated[uuid.UUID, Query(description="Node ID to filter by")],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[CommandHistoryResponse]:
    """Get command execution history for a node with cursor pagination."""
    audit.info(
        "api.v2.commands.history", node_id=str(node_id), cursor=cursor, limit=limit
    )  # noqa: E501
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    page_dto = await service.get_node_history(node_id, page=page, size=limit)
    items = [
        CommandHistoryResponse(
            id=item.id,
            command_fingerprint=item.command_fingerprint,
            exit_code=item.exit_code,
            stdout=item.stdout,
            stderr=item.stderr,
            stdout_bytes=item.stdout_bytes,
            stderr_bytes=item.stderr_bytes,
            truncated=item.truncated,
            started_at=item.started_at,
            finished_at=item.finished_at,
            created_at=item.created_at,
        )
        for item in page_dto.items
    ]
    has_more = (offset + len(items)) < page_dto.total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return CursorPage[CommandHistoryResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Stats — GET /stats ?node_id&date_from&date_to&group_by
# ---------------------------------------------------------------------------
