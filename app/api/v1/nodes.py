"""Node API endpoints."""

import uuid

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query

from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.schemas.node import (
    CommandRequest,
    CommandResult,
    NodeCreate,
    NodeResponse,
    NodeUpdate,
    PaginatedResponse,
)
from app.services.node_service import NodeService

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/", response_model=PaginatedResponse[NodeResponse])
@inject
async def get_nodes(
    service: FromDishka[NodeService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[NodeResponse]:
    """Get all nodes with pagination."""
    skip = (page - 1) * size
    nodes, total = await service.get_all_nodes(skip=skip, limit=size)
    return PaginatedResponse(items=nodes, total=total, page=page, size=size)


@router.get("/{node_id}", response_model=NodeResponse)
@inject
async def get_node(
    node_id: uuid.UUID, service: FromDishka[NodeService]
) -> NodeResponse:
    """Get a node by ID."""
    try:
        return await service.get_node(node_id)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail="Node not found")


@router.post("/", response_model=NodeResponse, status_code=201)
@inject
async def create_node(
    data: NodeCreate, service: FromDishka[NodeService]
) -> NodeResponse:
    """Create a new node."""
    return await service.create_node(data)


@router.put("/{node_id}", response_model=NodeResponse)
@inject
async def update_node(
    node_id: uuid.UUID, data: NodeUpdate, service: FromDishka[NodeService]
) -> NodeResponse:
    """Update an existing node."""
    try:
        return await service.update_node(node_id, data)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail="Node not found")


@router.delete("/{node_id}", status_code=204)
@inject
async def delete_node(node_id: uuid.UUID, service: FromDishka[NodeService]) -> None:
    """Delete a node."""
    try:
        await service.delete_node(node_id)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail="Node not found")


@router.post(
    "/{node_id}/check",
    response_model=NodeResponse,
)
@inject
async def check_node(
    node_id: uuid.UUID, service: FromDishka[NodeService]
) -> NodeResponse:
    """Check SSH connectivity to a node."""
    try:
        return await service.check_connectivity(node_id)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail="Node not found")
    except ConnectionFailedError as exc:
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
) -> CommandResult:
    """Execute a command on a node via SSH."""
    try:
        return await service.execute_command(node_id, data)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail="Node not found")
    except ConnectionFailedError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
