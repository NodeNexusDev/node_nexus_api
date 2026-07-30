"""Controlled Docker Compose operations for resilience E2E tests."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DockerServiceController:
    """Control services belonging to one exact pytest-docker Compose project."""

    compose_file: Path
    project_name: str

    def _compose(self, *args: str) -> str:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "-p",
                self.project_name,
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def _docker(self, *args: str) -> str:
        result = subprocess.run(
            ["docker", *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def container_id(self, service: str) -> str:
        """Return the container ID for a service in this Compose project."""
        container_id = self._compose("ps", "-q", service).strip()
        if not container_id:
            raise RuntimeError(
                f"Service {service!r} is not running in project {self.project_name!r}"
            )
        return container_id

    def restart(self, service: str) -> None:
        """Restart one Compose service."""
        self._compose("restart", service)

    def pause(self, service: str) -> None:
        """Pause one Compose service."""
        self._compose("pause", service)

    def unpause(self, service: str) -> None:
        """Unpause one Compose service."""
        self._compose("unpause", service)

    def disconnect_network(self, service: str) -> None:
        """Disconnect a service container from the project default network."""
        self._docker(
            "network",
            "disconnect",
            f"{self.project_name}_default",
            self.container_id(service),
        )

    def reconnect_network(self, service: str) -> None:
        """Reconnect a service container to the project default network."""
        self._docker(
            "network",
            "connect",
            f"{self.project_name}_default",
            self.container_id(service),
        )

    def logs(self, service: str, *, tail: int = 200) -> str:
        """Return recent logs for one service."""
        return self._compose("logs", "--no-color", "--tail", str(tail), service)
