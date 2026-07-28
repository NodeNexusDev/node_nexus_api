"""Docker target resolution and remote command execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory
    from app.repositories.node_repo import NodeRepository

from app.core.exceptions import ConnectionFailedError, DockerError, NodeNotFoundError
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.services.docker.command_builder import build_docker_command


class DockerCommandRunner:
    """Own the persistence-to-SSH boundary for Docker CLI operations."""

    def __init__(
        self,
        repository: NodeRepository,
        connector_factory: ConnectorFactory | None = None,
        node_reader: NodeConnectionReader | None = None,
    ) -> None:
        self._repository = repository
        self._connector_factory = connector_factory
        self._node_reader = node_reader

    async def get_target(self, node_id: UUID) -> Any:
        """Load and validate an immutable Docker connection target."""
        node = (
            await self._node_reader.get_connection(node_id)
            if self._node_reader
            else await self._repository.get_by_id(node_id)
        )
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        if node.connection_type != "docker":
            raise DockerError(f"Node {node_id} is not a Docker node")
        return node

    @staticmethod
    def build_command(node: Any, docker_args: str) -> str:
        """Build a Docker command for a target."""
        return build_docker_command(node, docker_args)

    async def execute(
        self, node: Any, command: str, timeout: int = 30
    ) -> tuple[str, str, int]:
        """Execute a Docker CLI command through a managed SSH connector."""
        connector = get_connector_factory(self._connector_factory).create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=decrypt_value(node.password),
            ssh_key=decrypt_value(node.ssh_key),
        )
        try:
            async with connector:
                return await connector.execute_command(command)
        except Exception as exc:
            raise ConnectionFailedError(
                f"Failed to connect to Docker host {node.host}: {exc}"
            ) from exc
