"""Node API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    CommandRequestDTO,
)
from app.schemas.common import CursorPage, decode_cursor
from app.schemas.node import (
    BulkCommandRequest,
    BulkCommandResult,
    BulkNodeResult,
    CommandRequest,
    CommandResult,
    CpuMetrics,
    DiskMetrics,
    MemoryMetrics,
    NodeCreate,
    NodeMetrics,
    NodeResponse,
    NodeUpdate,
    PaginatedResponse,
    TagAdd,
    TagRemove,
)
from app.services.node_bulk_command_service import NodeBulkCommandService
from app.services.node_command_service import NodeCommandService
from app.services.node_management_service import NodeManagementService
from app.services.node_metrics_service import NodeMetricsService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/nodes", tags=["nodes"], route_class=DishkaRoute)


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
        items, next_cursor, has_more = await service.get_nodes_cursor(
            cursor=decoded, limit=limit, tags=tag_list, search=search
        )
        return CursorPage(
            items=items, next_cursor=next_cursor, has_more=has_more, limit=limit
        )

    # Offset-based pagination (default)
    audit.info("api.nodes.list", page=page, size=size, tags=tag_list, search=search)
    nodes, total = await service.get_all_nodes(
        page=page, size=size, tags=tag_list, search=search
    )
    return PaginatedResponse(items=nodes, total=total, page=page, size=size)


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
    return await service.get_node(node_id)


@router.post("/", response_model=NodeResponse, status_code=201)
@inject
async def create_node(
    data: NodeCreate,
    service: FromDishka[NodeManagementService],
    _key: str = Security(require_write_scope),
) -> NodeResponse:
    """Create a new node."""
    audit.info("api.nodes.create", name=data.name, connection_type=data.connection_type)
    return await service.create_node(data)


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
    return await service.update_node(node_id, data)


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
    return await service.check_connectivity(node_id)


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
    return await service.add_tag(node_id, data)


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
    return await service.remove_tag(node_id, data)
