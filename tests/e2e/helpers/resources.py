"""Unique resource creation and deterministic cleanup for E2E tests."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import httpx2 as httpx


@dataclass
class CleanupRegistry:
    """Run registered cleanup actions in reverse creation order."""

    _actions: list[Callable[[], object]] = field(default_factory=list)

    def add(self, action: Callable[[], object]) -> None:
        """Register one cleanup action."""
        self._actions.append(action)

    def close(self) -> None:
        """Run all actions and report every cleanup failure together."""
        failures: list[str] = []
        while self._actions:
            action = self._actions.pop()
            try:
                action()
            except Exception as exc:  # cleanup must continue after one failure
                failures.append(f"{type(exc).__name__}: {exc}")
        if failures:
            raise AssertionError("E2E cleanup failures:\n" + "\n".join(failures))


class UniqueResourceFactory:
    """Create uniquely named API resources and register their cleanup."""

    def __init__(self, client: httpx.Client, cleanup: CleanupRegistry) -> None:
        self._client = client
        self._cleanup = cleanup

    @staticmethod
    def unique_name(prefix: str) -> str:
        """Return a short unique resource name."""
        return f"{prefix}-{uuid4().hex[:10]}"

    def _assert_created(self, response: httpx.Response) -> dict:
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        return response.json()

    def create_ssh_node(self, **overrides: object) -> dict:
        """Create an SSH node connected to the E2E SSH service."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-ssh"),
            "host": "ssh-server",
            "port": 2222,
            "connection_type": "ssh",
            "username": "testuser",
            "password": "testpass",
        }
        payload.update(overrides)
        node = self._assert_created(self._client.post("/api/v1/nodes/", json=payload))
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/nodes/{node['id']}"))
        return node

    def create_docker_node(self, **overrides: object) -> dict:
        """Create a Docker-capable SSH node connected to DinD."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-docker"),
            "host": "ssh-server",
            "port": 2222,
            "connection_type": "docker",
            "username": "testuser",
            "password": "testpass",
            "docker_host": "tcp://dind:2375",
        }
        payload.update(overrides)
        node = self._assert_created(self._client.post("/api/v1/nodes/", json=payload))
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/nodes/{node['id']}"))
        return node

    def create_command(self, command: str = "echo e2e", **overrides: object) -> dict:
        """Create a reusable command."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-command"),
            "command": command,
        }
        payload.update(overrides)
        item = self._assert_created(
            self._client.post("/api/v1/commands/", json=payload)
        )
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/commands/{item['id']}"))
        return item

    def create_script(self, **overrides: object) -> dict:
        """Create a one-step script."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-script"),
            "steps": [
                {
                    "label": "step-1",
                    "type": "inline",
                    "command": "echo e2e",
                }
            ],
        }
        payload.update(overrides)
        item = self._assert_created(self._client.post("/api/v1/scripts/", json=payload))
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/scripts/{item['id']}"))
        return item

    def create_api_key(self, **overrides: object) -> dict:
        """Create a managed API key."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-key"),
            "scope": "read-write",
        }
        payload.update(overrides)
        item = self._assert_created(
            self._client.post("/api/v1/api-keys/", json=payload)
        )
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/api-keys/{item['id']}"))
        return item

    def create_schedule(
        self,
        script_id: str,
        node_ids: list[str],
        cron: str = "* * * * *",
    ) -> dict:
        """Create or replace a script schedule."""
        response = self._client.post(
            f"/api/v1/scripts/{script_id}/schedule",
            json={"cron": cron, "node_ids": node_ids},
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        self._cleanup.add(
            lambda: self._client.delete(f"/api/v1/scripts/{script_id}/schedule")
        )
        return response.json()


@contextmanager
def resource_factory(client: httpx.Client) -> Generator[UniqueResourceFactory]:
    """Yield a resource factory and clean all registered resources."""
    registry = CleanupRegistry()
    try:
        yield UniqueResourceFactory(client, registry)
    finally:
        registry.close()
