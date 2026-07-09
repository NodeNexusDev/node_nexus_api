"""Node API endpoints."""

import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.node import NodeCreate, NodeResponse, NodeUpdate
from app.services.node_service import NodeService

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/", response_model=list[NodeResponse])
async def get_nodes(skip: int = 0, limit: int = 100) -> list[NodeResponse]:
    """Get all nodes."""
    service = NodeService(repository=None)  # TODO: inject via DI
    nodes = await service.get_all_nodes(skip=skip, limit=limit)
    return nodes


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: uuid.UUID) -> NodeResponse:
    """Get a node by ID."""
    service = NodeService(repository=None)  # TODO: inject via DI
    try:
        node = await service.get_node(node_id)
        return node
    except Exception:
        raise HTTPException(status_code=404, detail="Node not found")


@router.post("/", response_model=NodeResponse, status_code=201)
async def create_node(data: NodeCreate) -> NodeResponse:
    """Create a new node."""
    service = NodeService(repository=None)  # TODO: inject via DI
    node = await service.create_node(data)
    return node


@router.put("/{node_id}", response_model=NodeResponse)
async def update_node(node_id: uuid.UUID, data: NodeUpdate) -> NodeResponse:
    """Update an existing node."""
    service = NodeService(repository=None)  # TODO: inject via DI
    try:
        node = await service.update_node(node_id, data)
        return node
    except Exception:
        raise HTTPException(status_code=404, detail="Node not found")


@router.delete("/{node_id}", status_code=204)
async def delete_node(node_id: uuid.UUID) -> None:
    """Delete a node."""
    service = NodeService(repository=None)  # TODO: inject via DI
    try:
        await service.delete_node(node_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Node not found")
