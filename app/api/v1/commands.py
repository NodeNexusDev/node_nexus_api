"""Command API endpoints."""

import asyncio
import uuid
from datetime import datetime
from typing import Annotated

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import (
    Principal,
    get_current_principal,
    require_write_or_jwt_scope,
)
from app.application.command_policy import command_fingerprint
from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    CommandRequestDTO,
    CommandResultDTO,
)
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandExecuteRequestDTO,
    CommandParameterDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.application.dto.execution_lifecycle import CancelExecutionDTO, RetryCommandDTO
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.command_management_service import CommandManagementService
from app.application.services.execution_history_service import ExecutionHistoryService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_command_service import NodeCommandService
from app.core.template import render_command
from app.schemas.command import (
    CommandCreate,
    CommandExecuteRequest,
    CommandParameter,
    CommandResponse,
    CommandResult,
    CommandUpdate,
)
from app.schemas.common import PaginatedResponse
from app.schemas.execution_stats import ExecutionStatsResponse
from app.schemas.node import (
    BulkCancelCommandRequest,
    BulkCancelCommandResponse,
    BulkCancelCommandResult,
    BulkCommandHistoryItem,
    BulkCommandHistoryResponse,
    BulkCommandRequest,
    BulkCommandResult,
    BulkNodeResult,
    BulkRetryCommandRequest,
    BulkRetryCommandResponse,
    BulkRetryCommandResult,
    CommandExecuteRawRequest,
    CommandHistoryResponse,
    ExecutionRetryResponse,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/commands", tags=["commands"], route_class=DishkaRoute)


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


@router.get("/", response_model=PaginatedResponse[CommandResponse])
@inject
async def get_commands(
    service: FromDishka[CommandManagementService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None, description="Filter by tag (AND)"),
    search: str | None = Query(None, description="Search by name or description"),
    _key: Principal = Security(get_current_principal),
) -> PaginatedResponse[CommandResponse]:
    """Get all commands with pagination and optional search."""
    tag_list = [t.strip() for t in tag.split(",")] if tag else None
    audit.info(
        "api.commands.list",
        page=page,
        size=size,
        tags=tag_list,
        search=search,
    )
    commands, total = await service.get_all_commands(
        page=page,
        size=size,
        tags=tag_list,
        search=search,
    )
    return PaginatedResponse(
        items=[_command_response(command) for command in commands],
        total=total,
        page=page,
        size=size,
    )


@router.get("/tags", response_model=list[str])
@inject
async def get_command_tags(
    service: FromDishka[CommandManagementService],
    _key: Principal = Security(get_current_principal),
) -> list[str]:
    """Get all unique tags across all command templates."""
    audit.info("api.commands.tags.list")
    return await service.get_all_tags()


# --- Execution endpoints (moved from nodes) ---


@router.post("/execute", response_model=CommandResult)
@inject
async def execute_raw_command(
    data: CommandExecuteRawRequest,
    service: FromDishka[NodeCommandService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> CommandResult:
    """Execute a raw command on a node via SSH."""
    audit.info(
        "api.commands.execute",
        node_id=str(data.node_id),
        command_fingerprint=command_fingerprint(data.command),
        command_length=len(data.command),
    )
    result = await service.execute_command(
        data.node_id,
        CommandRequestDTO(command=data.command, timeout=data.timeout),
    )
    return CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
    )


@router.get("/history", response_model=PaginatedResponse[CommandHistoryResponse])
@inject
async def get_command_history(
    node_id: Annotated[uuid.UUID, Query(description="Node ID to filter by")],
    service: FromDishka[ExecutionHistoryService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: Principal = Security(get_current_principal),
) -> PaginatedResponse[CommandHistoryResponse]:
    """Get command execution history, optionally filtered by node."""
    audit.info("api.commands.history", node_id=str(node_id), page=page, size=size)
    page_dto = await service.get_node_history(node_id, page=page, size=size)
    return PaginatedResponse(
        items=[
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
        ],
        total=page_dto.total,
        page=page,
        size=size,
    )


@router.get("/stats", response_model=ExecutionStatsResponse)
@inject
async def get_node_command_stats(
    node_id: Annotated[uuid.UUID, Query(description="Node ID to filter by")],
    stats_service: FromDishka[ExecutionStatsService],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _key: Principal = Security(get_current_principal),
) -> ExecutionStatsResponse:
    """Get aggregated command execution stats for a node."""
    audit.info("api.commands.stats", node_id=str(node_id))
    stats = await stats_service.get_node_command_stats(
        node_id=node_id, date_from=date_from, date_to=date_to
    )
    return ExecutionStatsResponse.model_validate(stats)


@router.post(
    "/executions/{execution_id}/retry",
    response_model=ExecutionRetryResponse,
)
@inject
async def retry_command(
    execution_id: uuid.UUID,
    service: FromDishka[ExecutionLifecycleService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> ExecutionRetryResponse:
    """Retry a command execution."""
    audit.info("api.commands.executions.retry", execution_id=str(execution_id))
    result = await service.retry_command(RetryCommandDTO(execution_id=execution_id))
    return ExecutionRetryResponse(
        execution_id=result.execution_id,
        status=result.status,
        message="Command retry scheduled",
    )


# --- Bulk execution endpoints (moved from nodes_bulk) ---


@router.post("/bulk/execute", response_model=BulkCommandResult)
@inject
async def bulk_execute_raw_command(
    data: BulkCommandRequest,
    service: FromDishka[NodeBulkCommandService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkCommandResult:
    """Execute a raw command on multiple nodes by IDs and/or tags."""
    audit.info(
        "api.commands.bulk_execute",
        command_fingerprint=command_fingerprint(data.command),
        command_length=len(data.command),
        node_ids=[str(n) for n in (data.node_ids or [])],
        tags=data.tags,
    )
    result = await service.bulk_execute_command(
        BulkCommandRequestDTO(
            command=data.command,
            node_ids=tuple(data.node_ids or ()),
            tags=tuple(data.tags or ()),
        )
    )
    return BulkCommandResult(
        command=result.command,
        results=[
            BulkNodeResult(
                node_id=item.node_id,
                node_name=item.node_name,
                stdout=item.stdout,
                stderr=item.stderr,
                exit_code=item.exit_code,
            )
            for item in result.results
        ],
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
    )


@router.get("/bulk/history", response_model=BulkCommandHistoryResponse)
@inject
async def get_bulk_command_history(
    batch_id: Annotated[uuid.UUID, Query(description="Batch ID to retrieve")],
    service: FromDishka[ExecutionHistoryService],
    _key: Principal = Security(get_current_principal),
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BulkCommandHistoryResponse:
    """Return paginated command execution history for one bulk batch."""
    audit.info(
        "api.commands.bulk.history",
        batch_id=str(batch_id),
        page=page,
        size=size,
    )
    result = await service.get_batch_history(batch_id, page=page, size=size)
    return BulkCommandHistoryResponse(
        items=[BulkCommandHistoryItem.model_validate(item) for item in result.items],
        total=result.total,
        page=page,
        size=size,
    )


@router.post("/bulk/retry", response_model=BulkRetryCommandResponse)
@inject
async def bulk_retry_commands(
    data: BulkRetryCommandRequest,
    service: FromDishka[ExecutionLifecycleService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkRetryCommandResponse:
    """Retry multiple command executions."""
    audit.info(
        "api.commands.bulk_retry",
        execution_ids=[str(e) for e in data.execution_ids],
    )

    async def _retry_one(execution_id: uuid.UUID) -> BulkRetryCommandResult:
        try:
            await service.retry_command(RetryCommandDTO(execution_id=execution_id))
            return BulkRetryCommandResult(
                execution_id=str(execution_id), status="retry_scheduled"
            )
        except Exception as exc:
            return BulkRetryCommandResult(
                execution_id=str(execution_id), status="error", message=str(exc)
            )

    results = list(
        await asyncio.gather(*(_retry_one(eid) for eid in data.execution_ids))
    )
    succeeded = sum(1 for r in results if r.status == "retry_scheduled")
    return BulkRetryCommandResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


@router.post("/bulk/cancel", response_model=BulkCancelCommandResponse)
@inject
async def bulk_cancel_commands(
    data: BulkCancelCommandRequest,
    service: FromDishka[ExecutionLifecycleService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkCancelCommandResponse:
    """Cancel multiple running command executions."""
    audit.info(
        "api.commands.bulk_cancel",
        execution_ids=[str(e) for e in data.execution_ids],
    )

    async def _cancel_one(execution_id: uuid.UUID) -> BulkCancelCommandResult:
        try:
            await service.cancel_execution(
                CancelExecutionDTO(execution_id=execution_id)
            )
            return BulkCancelCommandResult(
                execution_id=str(execution_id),
                status="cancelled",
            )
        except Exception as exc:
            return BulkCancelCommandResult(
                execution_id=str(execution_id),
                status="error",
                message=str(exc),
            )

    results = list(
        await asyncio.gather(*(_cancel_one(eid) for eid in data.execution_ids))
    )
    succeeded = sum(1 for r in results if r.status == "cancelled")
    return BulkCancelCommandResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


# --- Command template CRUD ---


@router.get("/{command_id}", response_model=CommandResponse)
@inject
async def get_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandManagementService],
    _key: Principal = Security(get_current_principal),
) -> CommandResponse:
    """Get a command by ID."""
    audit.info("api.commands.get", command_id=str(command_id))
    return _command_response(await service.get_command(command_id))


@router.post("/", response_model=CommandResponse, status_code=201)
@inject
async def create_command(
    data: CommandCreate,
    service: FromDishka[CommandManagementService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> CommandResponse:
    """Create a new command template."""
    audit.info("api.commands.create", name=data.name)
    result = await service.create_command(
        CommandCreateDTO(
            name=data.name,
            description=data.description,
            command=data.command,
            parameters=tuple(_parameter_dto(item) for item in data.parameters),
            tags=tuple(data.tags),
        )
    )
    return _command_response(result)


@router.patch("/{command_id}", response_model=CommandResponse)
@inject
async def update_command(
    command_id: uuid.UUID,
    data: CommandUpdate,
    service: FromDishka[CommandManagementService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> CommandResponse:
    """Update an existing command template."""
    audit.info("api.commands.update", command_id=str(command_id))
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
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete a command template."""
    audit.info("api.commands.delete", command_id=str(command_id))
    await service.delete_command(command_id)


@router.post("/{command_id}/execute", response_model=CommandResult)
@inject
async def execute_command(
    command_id: uuid.UUID,
    data: CommandExecuteRequest,
    service: FromDishka[CommandExecutionService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> CommandResult:
    """Execute a command template on a node."""
    audit.info(
        "api.commands.execute",
        command_id=str(command_id),
        node_id=str(data.node_id),
    )
    result: CommandResultDTO = await service.execute_command(
        command_id,
        CommandExecuteRequestDTO(
            node_id=data.node_id,
            params=tuple(data.params.items()),
        ),
    )
    return CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
    )


@router.get("/{command_id}/stats", response_model=ExecutionStatsResponse)
@inject
async def get_command_stats(
    command_id: uuid.UUID,
    stats_service: FromDishka[ExecutionStatsService],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _key: Principal = Security(get_current_principal),
) -> ExecutionStatsResponse:
    audit.info("api.commands.stats", command_id=str(command_id))
    stats = await stats_service.get_command_stats(
        command_id=command_id, date_from=date_from, date_to=date_to
    )
    return ExecutionStatsResponse.model_validate(stats)


@router.post("/{command_id}/clone", response_model=CommandResponse)
@inject
async def clone_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandManagementService],
    new_name: str | None = Query(None),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> CommandResponse:
    """Clone a command template."""
    audit.info("api.commands.clone", command_id=str(command_id))
    cloned = await service.clone_command(command_id, new_name=new_name)
    return _command_response(cloned)


@router.post("/{command_id}/bulk-execute", response_model=BulkCommandResult)
@inject
async def bulk_execute_command(
    command_id: uuid.UUID,
    data: BulkCommandRequest,
    service: FromDishka[CommandManagementService],
    bulk_service: FromDishka[NodeBulkCommandService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkCommandResult:
    """Execute a command template on multiple nodes in parallel."""
    audit.info(
        "api.commands.bulk_execute",
        command_id=str(command_id),
        node_count=len(data.node_ids or []),
        tag_count=len(data.tags or []),
    )

    command = await service.get_command(command_id)
    rendered = render_command(
        command.command,
        [p.__dict__ for p in command.parameters] if command.parameters else [],
        data.params or {},
    )

    result = await bulk_service.execute(
        BulkCommandRequestDTO(
            command=rendered,
            node_ids=tuple(data.node_ids or ()),
            tags=tuple(data.tags or ()),
        )
    )
    return BulkCommandResult(
        command=result.command,
        results=[
            BulkNodeResult(
                node_id=item.node_id,
                node_name=item.node_name,
                stdout=item.stdout,
                stderr=item.stderr,
                exit_code=item.exit_code,
            )
            for item in result.results
        ],
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
    )
