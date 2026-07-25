"""Node API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.schemas.node import (
    BulkCommandRequest,
    BulkCommandResult,
    CommandRequest,
    CommandResult,
    NodeCreate,
    NodeMetrics,
    NodeResponse,
    NodeUpdate,
    PaginatedResponse,
    TagAdd,
    TagRemove,
)
from app.services.node_service import NodeService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/nodes", tags=["nodes"], route_class=DishkaRoute)


@router.get("/", response_model=PaginatedResponse[NodeResponse])
@inject
async def get_nodes(
    service: FromDishka[NodeService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tags: str | None = Query(None, description="Comma-separated tags (AND)"),
    search: str | None = Query(None, description="Search by name or host"),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[NodeResponse]:
    """Get all nodes with pagination, optional tag filtering and search."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    audit.info("api.nodes.list", page=page, size=size, tags=tag_list, search=search)
    nodes, total = await service.get_all_nodes(
        page=page, size=size, tags=tag_list, search=search
    )
    return PaginatedResponse(items=nodes, total=total, page=page, size=size)


@router.get("/tags")
@inject
async def get_all_tags(
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> list[str]:
    """Get all unique tags across all nodes."""
    audit.info("api.nodes.tags.list")
    return await service.get_all_tags()


@router.get("/{node_id}", response_model=NodeResponse)
@inject
async def get_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> NodeResponse:
    """Get a node by ID."""
    audit.info("api.nodes.get", node_id=str(node_id))
    try:
        return await service.get_node(node_id)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")


@router.post("/", response_model=NodeResponse, status_code=201)
@inject
async def create_node(
    data: NodeCreate,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> NodeResponse:
    """Create a new node."""
    audit.info("api.nodes.create", name=data.name, connection_type=data.connection_type)
    return await service.create_node(data)


@router.put("/{node_id}", response_model=NodeResponse)
@inject
async def update_node(
    node_id: uuid.UUID,
    data: NodeUpdate,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> NodeResponse:
    """Update an existing node."""
    audit.info("api.nodes.update", node_id=str(node_id))
    try:
        return await service.update_node(node_id, data)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")


@router.delete("/{node_id}", status_code=204)
@inject
async def delete_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> None:
    """Delete a node."""
    audit.info("api.nodes.delete", node_id=str(node_id))
    try:
        await service.delete_node(node_id)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")


@router.post("/bulk/execute", response_model=BulkCommandResult)
@inject
async def bulk_execute_command(
    data: BulkCommandRequest,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> BulkCommandResult:
    """Execute a command on multiple nodes by IDs and/or tags."""
    audit.info(
        "api.nodes.bulk_execute",
        command=data.command,
        node_ids=[str(n) for n in (data.node_ids or [])],
        tags=data.tags,
    )
    try:
        return await service.bulk_execute_command(data)
    except NodeNotFoundError as exc:
        audit.warning("api.nodes.bulk_execute.no_nodes", error=str(exc))
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/{node_id}/check",
    response_model=NodeResponse,
)
@inject
async def check_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> NodeResponse:
    """Check SSH connectivity to a node."""
    audit.info("api.nodes.check", node_id=str(node_id))
    try:
        return await service.check_connectivity(node_id)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")
    except ConnectionFailedError as exc:
        audit.error(
            "api.nodes.connection_failed",
            node_id=str(node_id),
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc))


@router.post(
    "/{node_id}/execute",
    response_model=CommandResult,
)
@inject
async def execute_command(
    node_id: uuid.UUID,
    data: CommandRequest,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> CommandResult:
    """Execute a command on a node via SSH."""
    audit.info("api.nodes.execute", node_id=str(node_id), command=data.command)
    try:
        return await service.execute_command(node_id, data)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")
    except ConnectionFailedError as exc:
        audit.error(
            "api.nodes.connection_failed",
            node_id=str(node_id),
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/{node_id}/metrics", response_model=NodeMetrics)
@inject
async def get_node_metrics(
    node_id: uuid.UUID,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> NodeMetrics:
    """Get system metrics from a node (CPU, memory, disk)."""
    audit.info("api.nodes.metrics", node_id=str(node_id))
    try:
        return await service.get_node_metrics(node_id)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")
    except ConnectionFailedError as exc:
        audit.error(
            "api.nodes.metrics_failed",
            node_id=str(node_id),
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{node_id}/tags", response_model=NodeResponse)
@inject
async def add_tag(
    node_id: uuid.UUID,
    data: TagAdd,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> NodeResponse:
    """Add a tag to a node."""
    audit.info("api.nodes.tags.add", node_id=str(node_id), tag=data.tag)
    try:
        return await service.add_tag(node_id, data)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")


@router.delete("/{node_id}/tags", response_model=NodeResponse)
@inject
async def remove_tag(
    node_id: uuid.UUID,
    data: TagRemove,
    service: FromDishka[NodeService],
    _key: str = Security(get_current_api_key),
) -> NodeResponse:
    """Remove a tag from a node."""
    audit.info("api.nodes.tags.remove", node_id=str(node_id), tag=data.tag)
    try:
        return await service.remove_tag(node_id, data)
    except NodeNotFoundError:
        audit.warning("api.nodes.not_found", node_id=str(node_id))
        raise HTTPException(status_code=404, detail="Node not found")
