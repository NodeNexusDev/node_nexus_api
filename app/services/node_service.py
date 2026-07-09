"""Node service for business logic."""

from uuid import UUID

from app.core.exceptions import NodeNotFoundError
from app.repositories.node_repo import NodeRepository
from app.schemas.node import NodeCreate, NodeResponse, NodeUpdate


class NodeService:
    """Service for node operations."""

    def __init__(self, repository: NodeRepository):
        self._repository = repository

    async def get_node(self, node_id: UUID) -> NodeResponse:
        """Get a node by ID."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return NodeResponse.model_validate(node)

    async def get_all_nodes(
        self, skip: int = 0, limit: int = 100
    ) -> list[NodeResponse]:
        """Get all nodes."""
        nodes = await self._repository.get_all(skip=skip, limit=limit)
        return [NodeResponse.model_validate(node) for node in nodes]

    async def create_node(self, data: NodeCreate) -> NodeResponse:
        """Create a new node."""
        node = await self._repository.create(data.model_dump())
        return NodeResponse.model_validate(node)

    async def update_node(self, node_id: UUID, data: NodeUpdate) -> NodeResponse:
        """Update an existing node."""
        update_data = data.model_dump(exclude_unset=True)
        node = await self._repository.update(node_id, update_data)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return NodeResponse.model_validate(node)

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node."""
        result = await self._repository.delete(node_id)
        if not result:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return True
