"""Node API endpoints."""

import uuid

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException

from app.core.exceptions import NodeNotFoundError
from app.schemas.node import NodeCreate, NodeResponse, NodeUpdate
from app.services.node_service import NodeService

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/", response_model=list[NodeResponse])
@inject
async def get_nodes(
    service: FromDishka[NodeService], skip: int = 0, limit: int = 100
) -> list[NodeResponse]:
    """Get all nodes."""
    return await service.get_all_nodes(skip=skip, limit=limit)


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
