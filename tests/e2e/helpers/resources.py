"""Unique resource creation and deterministic cleanup for E2E tests."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx

from tests.e2e.settings import (
    DEFAULT_DOCKER_IMAGE,
    DOCKER_HOST,
    SSH_HOST,
    SSH_KEY_PASSPHRASE,
    SSH_PASSWORD,
    SSH_PORT,
    SSH_USERNAME,
)
from tests.types import UnvalidatedJsonObject


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

    def _assert_created(self, response: httpx.Response) -> UnvalidatedJsonObject:
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        return response.json()

    def create_node(self, **overrides: object) -> UnvalidatedJsonObject:
        """Create a generic SSH node (legacy shape) with deterministic cleanup."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-node"),
            "host": SSH_HOST,
            "port": SSH_PORT,
            "connection_type": "ssh",
            "username": SSH_USERNAME,
            "password": SSH_PASSWORD,
        }
        payload.update(overrides)
        node = self._assert_created(self._client.post("/api/v1/nodes/", json=payload))
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/nodes/{node['id']}"))
        return node

    def create_ssh_node(self, **overrides: object) -> UnvalidatedJsonObject:
        """Create an SSH node connected to the E2E SSH service."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-ssh"),
            "host": SSH_HOST,
            "port": SSH_PORT,
            "connection_type": "ssh",
            "username": SSH_USERNAME,
            "password": SSH_PASSWORD,
        }
        payload.update(overrides)
        node = self._assert_created(self._client.post("/api/v1/nodes/", json=payload))
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/nodes/{node['id']}"))
        return node

    def create_ssh_key_node(
        self,
        *,
        encrypted: bool = False,
        **overrides: object,
    ) -> UnvalidatedJsonObject:
        """Create an SSH node with key-based authentication.

        Args:
            encrypted: If True, use the encrypted key + passphrase.
        """
        key_file = "test-key-enc" if encrypted else "test-key"
        host_key_path = Path(f"tests/ssh-keys/{key_file}")
        private_key = host_key_path.read_text()
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-ssh-key"),
            "host": SSH_HOST,
            "port": SSH_PORT,
            "connection_type": "ssh",
            "username": SSH_USERNAME,
            "ssh_key": private_key,
        }
        if encrypted:
            payload["passphrase"] = SSH_KEY_PASSPHRASE
        payload.update(overrides)
        node = self._assert_created(self._client.post("/api/v1/nodes/", json=payload))
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/nodes/{node['id']}"))
        return node

    def create_docker_node(self, **overrides: object) -> UnvalidatedJsonObject:
        """Create a Docker-capable SSH node connected to DinD."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-docker"),
            "host": SSH_HOST,
            "port": SSH_PORT,
            "connection_type": "docker",
            "username": SSH_USERNAME,
            "password": SSH_PASSWORD,
            "docker_host": DOCKER_HOST,
        }
        payload.update(overrides)
        node = self._assert_created(self._client.post("/api/v1/nodes/", json=payload))
        self._cleanup.add(lambda: self._client.delete(f"/api/v1/nodes/{node['id']}"))
        return node

    def create_container(
        self,
        node_id: str,
        image: str = DEFAULT_DOCKER_IMAGE,
        command: str = "sleep 300",
        **overrides: object,
    ) -> UnvalidatedJsonObject:
        """Create a Docker container via the API and register its cleanup.

        The container is created but not started; callers can start/stop/remove
        it as needed. Cleanup is best-effort and ignores 404 (already removed).
        """
        payload: dict[str, object] = {
            "image": image,
            "name": self.unique_name("e2e-ctr"),
            "command": command,
        }
        payload.update(overrides)
        response = self._client.post(
            f"/api/v1/nodes/{node_id}/docker/containers",
            json=payload,
        )
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        container = response.json()
        container_id = container["id"]
        self._cleanup.add(
            lambda: self._client.delete(
                f"/api/v1/nodes/{node_id}/docker/containers/{container_id}?force=true"
            )
        )
        return container

    def create_command(
        self, command: str = "echo e2e", **overrides: object
    ) -> UnvalidatedJsonObject:
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

    def create_script(self, **overrides: object) -> UnvalidatedJsonObject:
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

    def create_api_key(self, **overrides: object) -> UnvalidatedJsonObject:
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
    ) -> UnvalidatedJsonObject:
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

    def trigger_schedule_now(self, script_id: str) -> None:
        """Immediately trigger a scheduled script via the E2E harness endpoint."""
        response = self._client.post(
            f"/api/v1/internal/e2e/scheduler/{script_id}/trigger-now"
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )


@contextmanager
def resource_factory(client: httpx.Client) -> Generator[UniqueResourceFactory]:
    """Yield a resource factory and clean all registered resources."""
    registry = CleanupRegistry()
    try:
        yield UniqueResourceFactory(client, registry)
    finally:
        registry.close()
