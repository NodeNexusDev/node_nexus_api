"""Manage a standalone Docker Compose stack for middleware E2E tests."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx2 as httpx
import structlog

logger = structlog.get_logger()

_MASTER_API_KEY = "e2e-master-key-12345"


@dataclass(frozen=True)
class MiddlewareStackPorts:
    api_host: str
    api_port: int
    db_host: str
    db_port: int


class MiddlewareStackManager:
    """Start/stop a Docker Compose stack with custom middleware config."""

    def __init__(
        self,
        compose_file: Path,
        project_name: str,
        api_port: int,
        db_port: int,
    ) -> None:
        self._compose_file = compose_file
        self._project_name = project_name
        self._api_port = api_port
        self._db_port = db_port

    def _compose(self, *args: str) -> str:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self._compose_file),
                "-p",
                self._project_name,
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def up(self) -> MiddlewareStackPorts:
        """Start the stack and wait until API is ready."""
        self._compose("up", "-d", "--build", "--wait")

        # Wait for API readiness
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            try:
                resp = httpx.get(
                    f"http://127.0.0.1:{self._api_port}/ready",
                    headers={"X-API-Key": _MASTER_API_KEY},
                    timeout=2.0,
                )
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError(
                f"Stack {self._project_name} API did not become ready"
            )

        return MiddlewareStackPorts(
            api_host="127.0.0.1",
            api_port=self._api_port,
            db_host="127.0.0.1",
            db_port=self._db_port,
        )

    def down(self) -> None:
        """Stop and remove the stack."""
        try:
            self._compose("down", "-v", "--remove-orphans")
        except subprocess.CalledProcessError:
            logger.warning(
                "middleware.stack.down.failed",
                project=self._project_name,
            )

    def service_logs(self, service: str, *, tail: int = 100) -> str:
        """Return recent logs for a service."""
        return self._compose("logs", "--no-color", "--tail", str(tail), service)
