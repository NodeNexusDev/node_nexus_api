"""Docker target resolution and remote command execution."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.dto.node_connection import NodeConnectionDTO
    from app.application.ports.docker_runtime import DockerRuntime
    from app.application.ports.node_reader import NodeConnectionReader

from app.application.services.docker.command_builder import build_docker_command
from app.core.exceptions import DockerError, NodeNotFoundError


class DockerCommandRunner:
    """Resolve Docker targets and delegate ready commands to the runtime port."""

    def __init__(
        self,
        node_reader: NodeConnectionReader,
        runtime: DockerRuntime,
    ) -> None:
        self._node_reader = node_reader
        self._runtime = runtime

    async def get_target(self, node_id: UUID) -> NodeConnectionDTO:
        """Load and validate an immutable Docker connection target."""
        node = await self._node_reader.get_connection(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        if not node.is_docker_available:
            raise DockerError(f"Node {node_id} is not a Docker node (has_docker=false)")
        return node

    async def get_targets_by_tags(self, tags: list[str]) -> list[NodeConnectionDTO]:
        """Resolve node connection targets matching all ``tags``."""
        return await self._node_reader.get_connections_by_tags(tags)

    @staticmethod
    def build_command(node: NodeConnectionDTO, docker_args: str) -> str:
        """Build a Docker command for a target."""
        return build_docker_command(node, docker_args)

    async def execute(
        self, node: NodeConnectionDTO, command: str, timeout: int = 30
    ) -> tuple[str, str, int]:
        """Execute a ready Docker CLI command through the runtime port."""
        result = await self._runtime.execute(node, command, timeout)
        return result.stdout, result.stderr, result.exit_code
