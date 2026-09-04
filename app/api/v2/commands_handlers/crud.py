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
    CommandBulkUpdateRequest,
    CommandBulkUpdateResult,
    CommandCreate,
    CommandDeletionsRequest,
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
# Bulk update — PATCH /  (bulk-first, 207 on partial)
# ---------------------------------------------------------------------------


@router.patch("/", response_model=BulkResult[CommandBulkUpdateResult])
@inject
async def bulk_update_commands(
    data: CommandBulkUpdateRequest,
    service: FromDishka[CommandManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[CommandBulkUpdateResult]:
    """Bulk update commands via PATCH / (bulk-first, no bulk keyword)."""
    audit.info("api.v2.commands.bulk_update", count=len(data.updates))

    async def _update_one(item: Any) -> CommandBulkUpdateResult:  # noqa: ANN401
        try:
            changes = item.changes.model_dump(exclude_unset=True)
            if isinstance(changes.get("parameters"), list):
                changes["parameters"] = tuple(
                    CommandParameterDTO(**p) for p in changes["parameters"]
                )
            if isinstance(changes.get("tags"), list):
                changes["tags"] = tuple(changes["tags"])
            await service.update_command(
                item.id, CommandUpdateDTO(changes=tuple(changes.items()))
            )
            return CommandBulkUpdateResult(command_id=item.id, status="success")
        except Exception as exc:  # noqa: BLE001
            return CommandBulkUpdateResult(
                command_id=item.id, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_update_one(u) for u in data.updates))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[CommandBulkUpdateResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/deletions", response_model=BulkResult[CommandBulkUpdateResult])
@inject
async def bulk_delete_commands(
    data: CommandDeletionsRequest,
    service: FromDishka[CommandManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[CommandBulkUpdateResult]:
    """Bulk delete commands via POST /deletions (RESTful body, 207 on partial)."""
    audit.info("api.v2.commands.bulk_delete", count=len(data.ids))

    async def _delete_one(cid: uuid.UUID) -> CommandBulkUpdateResult:
        try:
            await service.delete_command(cid)
            return CommandBulkUpdateResult(command_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return CommandBulkUpdateResult(
                command_id=cid, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_delete_one(cid) for cid in data.ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[CommandBulkUpdateResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


# ---------------------------------------------------------------------------
# List — cursor pagination (translate cursor -> page)
# ---------------------------------------------------------------------------


@router.get("/{command_id}", response_model=CommandResponse)
@inject
async def get_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandManagementService],
    _principal: Principal = Security(get_current_principal),
) -> CommandResponse:
    """Get a command by ID."""
    audit.info("api.v2.commands.get", command_id=str(command_id))
    return _command_response(await service.get_command(command_id))


@router.patch("/{command_id}", response_model=CommandResponse)
@inject
async def update_command(
    command_id: uuid.UUID,
    data: CommandUpdate,
    service: FromDishka[CommandManagementService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> CommandResponse:
    """Update an existing command template."""
    audit.info("api.v2.commands.update", command_id=str(command_id))
    changes = data.model_dump(exclude_unset=True)
    if isinstance(changes.get("parameters"), list):
        changes["parameters"] = tuple(
            CommandParameterDTO(**parameter) for parameter in changes["parameters"]
        )
    if isinstance(changes.get("tags"), list):
        changes["tags"] = tuple(changes["tags"])
    result = await service.update_command(
        command_id,
        CommandUpdateDTO(changes=tuple(changes.items())),
    )
    return _command_response(result)


@router.delete("/{command_id}", status_code=204)
@inject
async def delete_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandManagementService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete a command template."""
    audit.info("api.v2.commands.delete", command_id=str(command_id))
    await service.delete_command(command_id)


@router.post("/{command_id}/clone", response_model=CommandResponse, status_code=201)
@inject
async def clone_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandManagementService],
    new_name: str | None = Query(None),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> CommandResponse:
    """Clone a command template."""
    audit.info("api.v2.commands.clone", command_id=str(command_id))
    cloned = await service.clone_command(command_id, new_name=new_name)
    return _command_response(cloned)


# ---------------------------------------------------------------------------
# Per-command stats — GET /{id}/stats ?date_from&date_to&group_by
# ---------------------------------------------------------------------------
