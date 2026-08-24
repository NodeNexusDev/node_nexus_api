"""Node API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.node_management import (
    NodeCreateDTO,
    NodeUpdateDTO,
)
from app.application.dto.node_status_history import (
    NodeStatusHistoryQueryDTO,
)
from app.application.dto.node_validation import NodeValidationRequestDTO
from app.application.dto.node_view import NodeViewDTO
from app.application.services.node_command_service import NodeCommandService
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)
from app.application.services.node_validation_service import NodeValidationService
from app.schemas.common import CursorPage, decode_cursor, encode_cursor
from app.schemas.node import (
    CpuMetrics,
    DiskMetrics,
    LoadAverage,
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
async def get_node_tags(
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


@router.patch("/{node_id}", response_model=NodeResponse)
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
        load_average=LoadAverage(
            one_min=result.load_average.one_min,
            five_min=result.load_average.five_min,
            fifteen_min=result.load_average.fifteen_min,
        ),
        uptime_since=result.uptime_since,
    )


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
