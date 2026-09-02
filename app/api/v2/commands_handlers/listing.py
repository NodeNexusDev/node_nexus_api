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


@router.get("/", response_model=CursorPage[CommandResponse])
@inject
async def list_commands(
    service: FromDishka[CommandManagementService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    tag: str | None = Query(None, description="Filter by single tag"),
    search: str | None = Query(None, description="Search by name or description"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[CommandResponse]:
    """List commands with cursor pagination (bulk-first).

    Cursor encodes an offset. Translated to page/size for the offset-based service.
    """
    tag_list = [tag] if tag else None
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    audit.info(
        "api.v2.commands.list", cursor=cursor, limit=limit, tag=tag, search=search
    )  # noqa: E501
    commands, total = await service.get_all_commands(
        page=page, size=limit, tags=tag_list, search=search
    )
    items = [_command_response(c) for c in commands]
    has_more = (offset + len(items)) < total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return CursorPage[CommandResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Bulk create — POST / with 207
# ---------------------------------------------------------------------------


@router.post("/", response_model=BulkResult[CommandBulkCreateResult], status_code=201)
@inject
async def bulk_create_commands(
    data: CommandBulkCreateRequest,
    service: FromDishka[CommandManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[CommandBulkCreateResult]:
    """Bulk create commands (1..20). Returns 207 when partially succeeded."""
    audit.info("api.v2.commands.bulk_create", count=len(data.items))

    async def _create_one(item: CommandCreate) -> CommandBulkCreateResult:
        try:
            dto = CommandCreateDTO(
                name=item.name,
                description=item.description,
                command=item.command,
                parameters=tuple(_parameter_dto(p) for p in item.parameters),
                tags=tuple(item.tags),
            )
            created = await service.create_command(dto)
            return CommandBulkCreateResult(
                id=created.id, name=created.name, status="success"
            )  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            return CommandBulkCreateResult(
                name=item.name, status="error", error=str(exc)
            )  # noqa: E501

    results = await asyncio.gather(*(_create_one(item) for item in data.items))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[CommandBulkCreateResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=list(results),
    )


# ---------------------------------------------------------------------------
# History — GET /history ?node_id&cursor&limit
# ---------------------------------------------------------------------------


