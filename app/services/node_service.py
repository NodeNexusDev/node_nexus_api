"""Node service for business logic."""

from uuid import UUID

from app.core.exceptions import NodeNotFoundError
from app.repositories.node_repo import NodeRepository
from app.schemas.node import NodeCreate, NodeUpdate


class NodeService:
    """Service for node operations."""

    def __init__(self, repository: NodeRepository):
        self._repository = repository

    async def get_node(self, node_id: UUID) -> dict:
        """Get a node by ID."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return {
            "id": node.id,
            "name": node.name,
            "host": node.host,
            "port": node.port,
            "connection_type": node.connection_type,
            "status": node.status,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    async def get_all_nodes(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """Get all nodes."""
        nodes = await self._repository.get_all(skip=skip, limit=limit)
        return [
            {
                "id": node.id,
                "name": node.name,
                "host": node.host,
                "port": node.port,
                "connection_type": node.connection_type,
                "status": node.status,
                "created_at": node.created_at,
                "updated_at": node.updated_at,
            }
            for node in nodes
        ]

    async def create_node(self, data: NodeCreate) -> dict:
        """Create a new node."""
        node = await self._repository.create(data.model_dump())
        return {
            "id": node.id,
            "name": node.name,
            "host": node.host,
            "port": node.port,
            "connection_type": node.connection_type,
            "status": node.status,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    async def update_node(self, node_id: UUID, data: NodeUpdate) -> dict:
        """Update an existing node."""
        update_data = data.model_dump(exclude_unset=True)
        node = await self._repository.update(node_id, update_data)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return {
            "id": node.id,
            "name": node.name,
            "host": node.host,
            "port": node.port,
            "connection_type": node.connection_type,
            "status": node.status,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node."""
        result = await self._repository.delete(node_id)
        if not result:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return True
