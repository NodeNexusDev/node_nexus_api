"""Docker CLI runtime capability port."""

from typing import Protocol

from app.application.dto.docker import DockerExecResultDTO
from app.application.dto.node_connection import NodeConnectionDTO


class DockerRuntime(Protocol):
    """Execute ready Docker CLI commands against immutable node targets."""

    async def execute(
        self,
        target: NodeConnectionDTO,
        command: str,
        timeout: int = 30,
    ) -> DockerExecResultDTO:
        """Execute a command produced by the pure Docker command builder."""
        ...
