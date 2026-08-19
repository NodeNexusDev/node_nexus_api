"""Node API endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.bulk_node_operation import (
    BulkNodeDeleteDTO,
    BulkNodeTagOperationDTO,
)
from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    CommandRequestDTO,
)
from app.application.dto.execution_lifecycle import RetryCommandDTO
from app.application.dto.node_management import (
    NodeCreateDTO,
    NodeTagDTO,
    NodeUpdateDTO,
)
from app.application.dto.node_status_history import (
    NodeStatusHistoryQueryDTO,
)
from app.application.dto.node_validation import NodeValidationRequestDTO
from app.application.dto.node_view import NodeViewDTO
from app.application.services.bulk_command_history_service import (
    BulkCommandHistoryService,
)
from app.application.services.command_history_service import CommandHistoryService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_command_service import NodeCommandService
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)
from app.application.services.node_validation_service import NodeValidationService
from app.schemas.common import CursorPage, decode_cursor, encode_cursor
from app.schemas.execution_stats import ExecutionStatsResponse
from app.schemas.node import (
    BulkCommandHistoryItem,
    BulkCommandHistoryResponse,
    BulkCommandRequest,
    BulkCommandResult,
    BulkNodeCheckRequest,
    BulkNodeDeleteRequest,
    BulkNodeOperationResult,
    BulkNodeResult,
    BulkNodeTagRequest,
    CommandHistoryResponse,
    CommandRequest,
    CommandResult,
    CpuMetrics,
    DiskMetrics,
    ExecutionRetryResponse,
    MemoryMetrics,
    NodeCreate,
    NodeMetrics,
    NodeResponse,
    NodeStatusHistoryItem,
    NodeStatusHistoryResponse,
    NodeUpdate,
    NodeValidateRequest,
    NodeValidateResponse,
    PaginatedResponse,
    TagAdd,
    TagRemove,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/nodes", tags=["nodes"], route_class=DishkaRoute)


def _node_response(node: NodeViewDTO) -> NodeResponse:
    """Map an application node view to the HTTP response schema."""
    return NodeResponse(
        id=node.id,
        name=node.name,
        host=node.host,
        port=node.port,
        connection_type=node.connection_type,
        status=node.status,
        username=node.username,
        docker_host=node.docker_host,
        tags=list(node.tags),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


@router.get("/")
@inject
async def get_nodes(
    service: FromDishka[NodeManagementService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tags: str | None = Query(None, description="Comma-separated tags (AND)"),
    search: str | None = Query(None, description="Search by name or host"),
    cursor: str | None = Query(None, description="Cursor for keyset pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _key: str = Security(get_current_api_key),
):
    """Get all nodes with pagination, optional tag filtering and search.

    Supports two pagination modes:
    - Offset-based (default): ?page=1&size=20
    - Cursor-based: ?cursor=<base64>&limit=20
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    if cursor is not None:
        # Cursor-based pagination
        try:
            decoded = decode_cursor(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        audit.info("api.nodes.list_cursor", limit=limit, tags=tag_list, search=search)
        items, next_cursor_key, has_more = await service.get_nodes_cursor(
            cursor=decoded, limit=limit, tags=tag_list, search=search
        )
        return CursorPage(
            items=[_node_response(node) for node in items],
            next_cursor=(
                encode_cursor(*next_cursor_key) if next_cursor_key is not None else None
            ),
            has_more=has_more,
            limit=limit,
        )

    # Offset-based pagination (default)
    audit.info("api.nodes.list", page=page, size=size, tags=tag_list, search=search)
    nodes, total = await service.get_all_nodes(
        page=page, size=size, tags=tag_list, search=search
    )
    return PaginatedResponse(
        items=[_node_response(node) for node in nodes],
        total=total,
        page=page,
        size=size,
    )


@router.get("/tags")
@inject
async def get_all_tags(
    service: FromDishka[NodeManagementService],
    _key: str = Security(get_current_api_key),
) -> list[str]:
    """Get all unique tags across all nodes."""
    audit.info("api.nodes.tags.list")
    return await service.get_all_tags()


@router.get("/{node_id}", response_model=NodeResponse)
@inject
async def get_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeManagementService],
    _key: str = Security(get_current_api_key),
) -> NodeResponse:
    """Get a node by ID."""
    audit.info("api.nodes.get", node_id=str(node_id))
    return _node_response(await service.get_node(node_id))


@router.post("/", response_model=NodeResponse, status_code=201)
@inject
async def create_node(
    data: NodeCreate,
    service: FromDishka[NodeManagementService],
    _key: str = Security(require_write_scope),
) -> NodeResponse:
    """Create a new node."""
    audit.info("api.nodes.create", name=data.name, connection_type=data.connection_type)
    return _node_response(
        await service.create_node(
            NodeCreateDTO(
                name=data.name,
                host=data.host,
                port=data.port,
                connection_type=data.connection_type,
                username=data.username,
                password=data.password,
                ssh_key=data.ssh_key,
                passphrase=data.passphrase,
                docker_host=data.docker_host,
                tags=tuple(data.tags),
            )
        )
    )


@router.put("/{node_id}", response_model=NodeResponse)
@inject
async def update_node(
    node_id: uuid.UUID,
    data: NodeUpdate,
    service: FromDishka[NodeManagementService],
    _key: str = Security(require_write_scope),
) -> NodeResponse:
    """Update an existing node."""
    audit.info("api.nodes.update", node_id=str(node_id))
    changes = data.model_dump(exclude_unset=True)
    if isinstance(changes.get("tags"), list):
        changes["tags"] = tuple(changes["tags"])
    return _node_response(
        await service.update_node(
            node_id,
            NodeUpdateDTO(changes=tuple(changes.items())),
        )
    )


@router.delete("/{node_id}", status_code=204)
@inject
async def delete_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeManagementService],
    _key: str = Security(require_write_scope),
) -> None:
    """Delete a node."""
    audit.info("api.nodes.delete", node_id=str(node_id))
    await service.delete_node(node_id)


@router.post("/bulk/execute", response_model=BulkCommandResult)
@inject
async def bulk_execute_command(
    data: BulkCommandRequest,
    service: FromDishka[NodeBulkCommandService],
    _key: str = Security(require_write_scope),
) -> BulkCommandResult:
    """Execute a command on multiple nodes by IDs and/or tags."""
    audit.info(
        "api.nodes.bulk_execute",
        command=data.command,
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
    service: FromDishka[BulkCommandHistoryService],
    _key: str = Security(get_current_api_key),
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BulkCommandHistoryResponse:
    """Return paginated command execution history for one bulk batch."""
    result = await service.get_batch_history(batch_id, page=page, size=size)
    return BulkCommandHistoryResponse(
        items=[BulkCommandHistoryItem.model_validate(item) for item in result.items],
        total=result.total,
        page=page,
        size=size,
    )


@router.post(
    "/{node_id}/check",
    response_model=NodeResponse,
)
@inject
async def check_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeCommandService],
    _key: str = Security(require_write_scope),
) -> NodeResponse:
    """Check SSH connectivity to a node."""
    audit.info("api.nodes.check", node_id=str(node_id))
    result = await service.check_connectivity(node_id)
    return NodeResponse(
        id=result.id,
        name=result.name,
        host=result.host,
        port=result.port,
        connection_type=result.connection_type,
        status=result.status,
        username=result.username,
        docker_host=result.docker_host,
        tags=list(result.tags),
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.post("/validate-credentials", response_model=NodeValidateResponse)
@inject
async def validate_credentials(
    data: NodeValidateRequest,
    service: FromDishka[NodeValidationService],
    _key: str = Security(require_write_scope),
) -> NodeValidateResponse:
    """Validate SSH credentials without saving a node."""
    audit.info("api.nodes.validate_credentials", host=data.host, port=data.port)
    result = await service.validate_credentials(
        NodeValidationRequestDTO(
            host=data.host,
            port=data.port,
            connection_type=data.connection_type,
            username=data.username,
            password=data.password,
            ssh_key=data.ssh_key,
            passphrase=data.passphrase,
        )
    )
    return NodeValidateResponse(
        status=result.status,
        message=result.message,
    )


@router.post(
    "/{node_id}/execute",
    response_model=CommandResult,
)
@inject
async def execute_command(
    node_id: uuid.UUID,
    data: CommandRequest,
    service: FromDishka[NodeCommandService],
    _key: str = Security(require_write_scope),
) -> CommandResult:
    """Execute a command on a node via SSH."""
    audit.info("api.nodes.execute", node_id=str(node_id), command=data.command)
    result = await service.execute_command(
        node_id,
        CommandRequestDTO(command=data.command, timeout=data.timeout),
    )
    return CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
    )


@router.get(
    "/{node_id}/commands/history",
    response_model=PaginatedResponse[CommandHistoryResponse],
)
@inject
async def get_command_history(
    node_id: uuid.UUID,
    service: FromDishka[CommandHistoryService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[CommandHistoryResponse]:
    """Get command execution history for a node."""
    audit.info("api.nodes.commands.history", node_id=str(node_id), page=page, size=size)
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


@router.get("/{node_id}/metrics", response_model=NodeMetrics)
@inject
async def get_node_metrics(
    node_id: uuid.UUID,
    service: FromDishka[NodeMetricsService],
    _key: str = Security(get_current_api_key),
) -> NodeMetrics:
    """Get system metrics from a node (CPU, memory, disk)."""
    audit.info("api.nodes.metrics", node_id=str(node_id))
    result = await service.get_node_metrics(node_id)
    return NodeMetrics(
        cpu=CpuMetrics(
            usage_percent=result.cpu.usage_percent,
            cores=result.cpu.cores,
        ),
        memory=MemoryMetrics(
            total_bytes=result.memory.total_bytes,
            used_bytes=result.memory.used_bytes,
            percent=result.memory.percent,
        ),
        disk=DiskMetrics(
            total_bytes=result.disk.total_bytes,
            used_bytes=result.disk.used_bytes,
            percent=result.disk.percent,
        ),
        uptime_since=result.uptime_since,
    )


@router.post("/{node_id}/tags", response_model=NodeResponse)
@inject
async def add_tag(
    node_id: uuid.UUID,
    data: TagAdd,
    service: FromDishka[NodeManagementService],
    _key: str = Security(require_write_scope),
) -> NodeResponse:
    """Add a tag to a node."""
    audit.info("api.nodes.tags.add", node_id=str(node_id), tag=data.tag)
    return _node_response(await service.add_tag(node_id, NodeTagDTO(tag=data.tag)))


@router.delete("/{node_id}/tags", response_model=NodeResponse)
@inject
async def remove_tag(
    node_id: uuid.UUID,
    data: TagRemove,
    service: FromDishka[NodeManagementService],
    _key: str = Security(require_write_scope),
) -> NodeResponse:
    """Remove a tag from a node."""
    audit.info("api.nodes.tags.remove", node_id=str(node_id), tag=data.tag)
    return _node_response(await service.remove_tag(node_id, NodeTagDTO(tag=data.tag)))


@router.get(
    "/{node_id}/status-history",
    response_model=NodeStatusHistoryResponse,
)
@inject
async def get_node_status_history(
    node_id: uuid.UUID,
    service: FromDishka[NodeStatusHistoryService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> NodeStatusHistoryResponse:
    """Get status change history for a node."""
    audit.info("api.nodes.status_history", node_id=str(node_id), page=page, size=size)
    query = NodeStatusHistoryQueryDTO(
        node_id=node_id,
        offset=(page - 1) * size,
        limit=size,
    )
    result = await service.get_history(query)
    return NodeStatusHistoryResponse(
        items=[
            NodeStatusHistoryItem(
                id=item.id,
                node_id=item.node_id,
                old_status=item.old_status,
                new_status=item.new_status,
                source=item.source,
                changed_at=item.changed_at,
            )
            for item in result.items
        ],
        total=result.total,
        page=page,
        size=size,
    )


# --- Bulk node operations ---


@router.post("/bulk/delete", response_model=BulkNodeOperationResult)
@inject
async def bulk_delete_nodes(
    data: BulkNodeDeleteRequest,
    service: FromDishka[NodeBulkOperationService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Delete multiple nodes by IDs."""
    audit.info(
        "api.nodes.bulk_delete",
        node_ids=[str(n) for n in data.node_ids],
    )
    result = await service.bulk_delete(BulkNodeDeleteDTO(node_ids=tuple(data.node_ids)))
    return BulkNodeOperationResult(
        affected=result.affected,
        node_ids=list(result.node_ids),
    )


@router.post("/bulk/tags/add", response_model=BulkNodeOperationResult)
@inject
async def bulk_add_tags(
    data: BulkNodeTagRequest,
    service: FromDishka[NodeBulkOperationService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Add tags to multiple nodes."""
    audit.info(
        "api.nodes.bulk_tags_add",
        node_ids=[str(n) for n in data.node_ids],
        tags=data.tags,
    )
    result = await service.bulk_add_tags(
        BulkNodeTagOperationDTO(
            node_ids=tuple(data.node_ids),
            tags=tuple(data.tags),
        )
    )
    return BulkNodeOperationResult(
        affected=result.affected,
        node_ids=list(result.node_ids),
    )


@router.post("/bulk/tags/remove", response_model=BulkNodeOperationResult)
@inject
async def bulk_remove_tags(
    data: BulkNodeTagRequest,
    service: FromDishka[NodeBulkOperationService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Remove tags from multiple nodes."""
    audit.info(
        "api.nodes.bulk_tags_remove",
        node_ids=[str(n) for n in data.node_ids],
        tags=data.tags,
    )
    result = await service.bulk_remove_tags(
        BulkNodeTagOperationDTO(
            node_ids=tuple(data.node_ids),
            tags=tuple(data.tags),
        )
    )
    return BulkNodeOperationResult(
        affected=result.affected,
        node_ids=list(result.node_ids),
    )


@router.post("/bulk/check", response_model=BulkNodeOperationResult)
@inject
async def bulk_check_nodes(
    data: BulkNodeCheckRequest,
    service: FromDishka[NodeCommandService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Check SSH connectivity for multiple nodes."""
    import asyncio

    audit.info(
        "api.nodes.bulk_check",
        node_ids=[str(n) for n in data.node_ids],
    )
    results = await asyncio.gather(
        *(service.check_connectivity(node_id) for node_id in data.node_ids),
        return_exceptions=True,
    )
    succeeded_ids = [
        str(data.node_ids[i])
        for i, r in enumerate(results)
        if not isinstance(r, Exception)
    ]
    return BulkNodeOperationResult(
        affected=len(succeeded_ids),
        node_ids=data.node_ids,
    )


@router.post(
    "/{node_id}/commands/{execution_id}/retry",
    response_model=ExecutionRetryResponse,
)
@inject
async def retry_command(
    node_id: uuid.UUID,
    execution_id: uuid.UUID,
    service: FromDishka[ExecutionLifecycleService],
    _key: str = Security(require_write_scope),
) -> ExecutionRetryResponse:
    """Retry a command execution."""
    audit.info(
        "api.nodes.commands.retry",
        node_id=str(node_id),
        execution_id=str(execution_id),
    )
    result = await service.retry_command(
        RetryCommandDTO(execution_id=execution_id, node_id=node_id)
    )
    return ExecutionRetryResponse(
        execution_id=result.execution_id,
        status=result.status,
        message="Command retry scheduled",
    )


@router.get("/{node_id}/stats", response_model=ExecutionStatsResponse)
@inject
async def get_node_stats(
    node_id: uuid.UUID,
    stats_service: FromDishka[ExecutionStatsService],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _key: str = Security(get_current_api_key),
) -> ExecutionStatsResponse:
    audit.info("api.nodes.stats", node_id=str(node_id))
    stats = await stats_service.get_node_command_stats(
        node_id=node_id, date_from=date_from, date_to=date_to
    )
    return ExecutionStatsResponse.model_validate(stats)
