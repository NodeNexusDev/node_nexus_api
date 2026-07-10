"""Node service for business logic."""

from uuid import UUID

import structlog

from app.core.connectors.ssh import SSHConnector
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.repositories.node_repo import NodeRepository
from app.schemas.node import (
    CommandRequest,
    CommandResult,
    NodeCreate,
    NodeResponse,
    NodeUpdate,
)

logger = structlog.get_logger()


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

    def _build_connector(self, node: NodeResponse) -> SSHConnector:
        """Build an SSH connector from node data."""
        return SSHConnector(
            host=node.host,
            port=node.port,
            username=node.username,
        )

    async def check_connectivity(self, node_id: UUID) -> NodeResponse:
        """Check SSH connectivity to a node and update its status."""
        node = await self.get_node(node_id)
        connector = self._build_connector(node)

        try:
            async with connector:
                await connector.execute_command("echo ok")
            new_status = "active"
            logger.info("node.connectivity.ok", node_id=str(node_id))
        except Exception as exc:
            new_status = "unreachable"
            logger.warning(
                "node.connectivity.failed",
                node_id=str(node_id),
                error=str(exc),
            )

        updated = await self._repository.update(node_id, {"status": new_status})
        return NodeResponse.model_validate(updated)

    async def execute_command(
        self, node_id: UUID, data: CommandRequest
    ) -> CommandResult:
        """Execute a command on a node via SSH."""
        node = await self.get_node(node_id)
        connector = self._build_connector(node)

        try:
            async with connector:
                result = await connector.execute_command(data.command)
            logger.info(
                "node.command.executed",
                node_id=str(node_id),
                command=data.command,
            )
            return CommandResult(
                stdout=result,
                stderr="",
                exit_code=0,
            )
        except Exception as exc:
            logger.error(
                "node.command.failed",
                node_id=str(node_id),
                command=data.command,
                error=str(exc),
            )
            raise ConnectionFailedError(
                f"Failed to execute command on node {node_id}: {exc}"
            ) from exc
