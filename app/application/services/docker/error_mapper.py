"""Docker CLI exit-status to domain-error translation."""

from app.core.exceptions import (
    ContainerNotFoundError,
    DockerDaemonError,
    DockerError,
    ImageNotFoundError,
)


def raise_for_docker_error(stderr: str, exit_code: int) -> None:
    """Raise the most specific domain error for failed Docker CLI output."""
    if exit_code == 0:
        return
    normalized = stderr.lower()
    if (
        "no such container" in normalized
        or "no such image or container" in normalized
        or "no such object" in normalized
    ):
        raise ContainerNotFoundError(stderr)
    if "no such image" in normalized:
        raise ImageNotFoundError(stderr)
    if "cannot connect to the docker daemon" in normalized:
        raise DockerDaemonError(stderr)
    if "is not running" in normalized:
        raise DockerError(stderr)
    raise DockerError(f"Docker command failed (exit {exit_code}): {stderr}")
