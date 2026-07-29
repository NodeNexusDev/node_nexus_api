"""Docker CLI runtime capability port."""

from typing import Protocol

from app.application.dto.docker import DockerExecResultDTO
from app.application.dto.node_connection import NodeConnectionDTO


class DockerRuntime(Protocol):
    """Execute Docker CLI arguments against an immutable node target."""

    async def execute(
        self,
        target: NodeConnectionDTO,
        docker_args: str,
        timeout: int = 30,
    ) -> DockerExecResultDTO:
        """Execute Docker CLI arguments and return the process result."""
        ...
