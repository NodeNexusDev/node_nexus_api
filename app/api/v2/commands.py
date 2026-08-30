"""Command API v2 — bulk-first without bulk keyword."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security
from pydantic import BaseModel, Field

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
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
from app.core.types import JsonObject
from app.schemas.command import (
    CommandCreate,
    CommandParameter,
    CommandResponse,
    CommandUpdate,
)
from app.schemas.common import BulkResult, CursorPage
from app.schemas.execution_stats import ExecutionStatsResponse
from app.schemas.node import (
    BulkCancelCommandResult,
    BulkRetryCommandResult,
    CommandHistoryResponse,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/commands", tags=["commands"], route_class=DishkaRoute)


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


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor for pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


# ---------------------------------------------------------------------------
# Schemas for v2 bulk-first (no bulk keyword)
# ---------------------------------------------------------------------------


class CommandBulkCreateRequest(BaseModel):
    """Bulk create commands (1..20)."""

    items: list[CommandCreate] = Field(min_length=1, max_length=20)


class CommandBulkCreateResult(BaseModel):
    """Result of creating a single command."""

    id: uuid.UUID | None = None
    name: str | None = None
    status: Literal["success", "error"]
    error: str = ""


class StatsBucket(BaseModel):
    """Single time bucket for stats grouping."""

    period: str
    total: int
    successful: int
    failed: int
    cancelled: int
    avg_duration_ms: float | None = None


class StatsBucketsResponse(BaseModel):
    """Buckets response when group_by is present."""

    buckets: list[StatsBucket]


class CommandExecutionsRequest(BaseModel):
    """M×N command executions (command_ids × nodes)."""

    command_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    params: dict[str, JsonObject] = Field(default_factory=dict)

    @property
    def _estimated_n(self) -> int:
        # best-effort M*N check without resolving tags
        n = len(self.node_ids) if self.node_ids else (len(self.node_tags) or 1)
        return len(self.command_ids) * n


class RawExecutionsRequest(BaseModel):
    """Bulk raw command executions."""

    commands: list[str] = Field(min_length=1, max_length=20)
    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)


class BulkExecutionItem(BaseModel):
    """Result of a single command execution on a single node."""

    command_id: uuid.UUID | None = None
    command: str | None = None
    node_id: uuid.UUID | None = None
    node_name: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    status: Literal["success", "error"]
    error: str = ""


class BulkExecutionBatchResponse(BaseModel):
    """Batch response for M×N executions."""

    batch_id: uuid.UUID
    total: int
    succeeded: int
    failed: int
    results: list[BulkExecutionItem]


class ExecutionRetriesRequest(BaseModel):
    """Request to retry multiple executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ExecutionCancelsRequest(BaseModel):
    """Request to cancel multiple executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


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
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
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
    next_cursor = _encode_offset(offset + limit) if has_more else None
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
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[CommandBulkCreateResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=list(results),
    )


# ---------------------------------------------------------------------------
# History — GET /history ?node_id&cursor&limit
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
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
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
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[CommandHistoryResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Stats — GET /stats ?node_id&date_from&date_to&group_by
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
) -> Any:
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
                raw_params,  # type: ignore[arg-type]
            )
            result = await bulk_service.execute(
                BulkCommandRequestDTO(
                    command=rendered,
                    node_ids=tuple(data.node_ids),
                    tags=tuple(data.node_tags),
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
    if failed > 0 and succeeded > 0:
        response.status_code = 207
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
            result = await bulk_service.execute(
                BulkCommandRequestDTO(
                    command=command,
                    node_ids=tuple(data.node_ids),
                    tags=tuple(data.node_tags),
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
    if failed > 0 and succeeded > 0:
        response.status_code = 207
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


@router.get("/executions/history", response_model=CursorPage[CommandHistoryResponse])
@inject
async def get_executions_history(
    batch_id: Annotated[uuid.UUID, Query(description="Batch ID to retrieve")],
    service: FromDishka[ExecutionHistoryService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[CommandHistoryResponse]:
    """Return paginated execution history for one bulk batch with cursor."""
    audit.info(
        "api.v2.commands.executions.history",
        batch_id=str(batch_id),
        cursor=cursor,
        limit=limit,
    )  # noqa: E501
    offset = 0
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    result = await service.get_batch_history(batch_id, page=page, size=limit)
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
        for item in result.items
    ]
    has_more = (offset + len(items)) < result.total
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[CommandHistoryResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Executions retries / cancels — POST /executions/retries , /cancels
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
    if failed > 0 and succeeded > 0:
        response.status_code = 207
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
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkCancelCommandResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Single command CRUD + clone
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


@router.get("/{command_id}/stats")
@inject
async def get_command_stats(
    command_id: uuid.UUID,
    stats_service: FromDishka[ExecutionStatsService],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    group_by: Literal["hour", "day", "week", "month"] | None = Query(None),
    _principal: Principal = Security(get_current_principal),
) -> Any:
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
