"""Safe Docker CLI command construction."""

import shlex

from app.application.dto.node_connection import NodeConnectionDTO


def build_docker_command(node: NodeConnectionDTO, docker_args: str) -> str:
    """Build a Docker CLI command with an escaped optional daemon endpoint."""
    if node.docker_host:
        return f"DOCKER_HOST={shlex.quote(node.docker_host)} docker {docker_args}"
    return f"docker {docker_args}"
