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
        """Assert single-resource creation (201) or bulk envelope (200/201/207)."""
        # Bulk envelope fallback: if response contains BulkResult, unwrap first success.
        if response.status_code in (200, 201, 207):
            try:
                data = response.json()
            except Exception:
                data = None
            if isinstance(data, dict) and "results" in data:
                results = data.get("results")
                if isinstance(results, list) and results:
                    first = results[0]
                    if isinstance(first, dict) and first.get("status") != "success":
                        raise AssertionError(
                            f"Bulk create failed: {first.get('error')} "
                            f"status={response.status_code} body={response.text}"
                        )
                    # Try to synthesize compat dict if we can detect id field
                    raw_id = None
                    if isinstance(first, dict):
                        raw_id = first.get("node_id") or first.get("id")
                    if raw_id is not None:
                        compat: UnvalidatedJsonObject = {"id": str(raw_id)}
                        if isinstance(first, dict):
                            for k, v in first.items():
                                if k not in compat:
                                    compat[k] = v
                        return compat
                # Fallback: return bulk data as-is if unwrapping not applicable
                return data  # type: ignore[return-value]
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        return response.json()  # type: ignore[no-any-return]

    def _unwrap_bulk(
        self,
        response: httpx.Response,
        payload: dict[str, object],
        *,
        id_field: str = "node_id",
    ) -> UnvalidatedJsonObject:
        """Handle bulk-first API (201/207 BulkResult) with legacy fallback.

        Sends ``{"items": [payload]}``; expects ``BulkResult`` with
        ``results=[{node_id|id,status,error}]``. On success returns a
        backward-compatible dict with ``id`` plus payload fields.
        If the response is a legacy single object (no ``results``), it is
        returned directly.
        """
        assert response.status_code in (200, 201, 207), (
            f"Expected 200/201/207, got {response.status_code}: {response.text}"
        )
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
            assert isinstance(results, list) and len(results) > 0, (
                f"Expected non-empty results, got {data}"
            )
            first = results[0]
            assert isinstance(first, dict), f"Expected dict result, got {first}"
            if first.get("status") == "error":
                raise AssertionError(
                    f"Bulk create failed: {first.get('error')} payload={payload} "
                    f"response={data}"
                )
            raw_id = first.get(id_field)
            if raw_id is None:
                # fallback for id vs node_id naming differences
                raw_id = first.get("id") or first.get("node_id")
            assert raw_id is not None, f"Missing id in bulk result: {first}"
            node_id = str(raw_id)
            # Backward-compatible synthesis: payload fields + id + bulk result extras
            compat: UnvalidatedJsonObject = dict(payload)
            compat["id"] = node_id
            # Preserve bulk fields without overwriting payload's explicit keys
            for k, v in first.items():
                if k not in compat:
                    compat[k] = v
            # Ensure string id always present
            compat["id"] = node_id
            # Also expose node_id for node bulk results
            if id_field == "node_id" and "node_id" not in compat:
                compat["node_id"] = node_id
            return compat
        # Legacy single response fallback
        assert response.status_code == 201, (
            f"Expected 201 for legacy, got {response.status_code}: {response.text}"
        )
        assert isinstance(data, dict), f"Expected dict, got {data}"
        return data  # type: ignore[return-value]

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
        response = self._client.post("/api/v2/nodes/", json={"items": [payload]})
        # Fallback if server still expects single payload (422)
        if response.status_code == 422:
            # Try legacy single shape once
            alt = self._client.post("/api/v2/nodes/", json=payload)
            if alt.status_code in (200, 201, 207):
                response = alt
        node = self._unwrap_bulk(response, payload, id_field="node_id")
        nid = str(node["id"])
        self._cleanup.add(
            lambda nid=nid: self._client.delete(f"/api/v2/nodes/{nid}")  # type: ignore[misc]
        )
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
        response = self._client.post("/api/v2/nodes/", json={"items": [payload]})
        if response.status_code == 422:
            alt = self._client.post("/api/v2/nodes/", json=payload)
            if alt.status_code in (200, 201, 207):
                response = alt
        node = self._unwrap_bulk(response, payload, id_field="node_id")
        nid = str(node["id"])
        self._cleanup.add(
            lambda nid=nid: self._client.delete(f"/api/v2/nodes/{nid}")  # type: ignore[misc]
        )
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
        response = self._client.post("/api/v2/nodes/", json={"items": [payload]})
        if response.status_code == 422:
            alt = self._client.post("/api/v2/nodes/", json=payload)
            if alt.status_code in (200, 201, 207):
                response = alt
        node = self._unwrap_bulk(response, payload, id_field="node_id")
        nid = str(node["id"])
        self._cleanup.add(
            lambda nid=nid: self._client.delete(f"/api/v2/nodes/{nid}")  # type: ignore[misc]
        )
        return node

    def create_docker_node(self, **overrides: object) -> UnvalidatedJsonObject:
        """Create a Docker-capable SSH node connected to DinD."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-docker"),
            "host": SSH_HOST,
            "port": SSH_PORT,
            "connection_type": "ssh",
            "has_docker": True,
            "username": SSH_USERNAME,
            "password": SSH_PASSWORD,
            "docker_host": DOCKER_HOST,
        }
        payload.update(overrides)
        response = self._client.post("/api/v2/nodes/", json={"items": [payload]})
        if response.status_code == 422:
            alt = self._client.post("/api/v2/nodes/", json=payload)
            if alt.status_code in (200, 201, 207):
                response = alt
        node = self._unwrap_bulk(response, payload, id_field="node_id")
        nid = str(node["id"])
        self._cleanup.add(
            lambda nid=nid: self._client.delete(f"/api/v2/nodes/{nid}")  # type: ignore[misc]
        )
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
            f"/api/v2/nodes/{node_id}/docker/containers",
            json=payload,
        )
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        container = response.json()
        container_id = container["id"]
        self._cleanup.add(
            lambda nid=node_id, cid=container_id: self._client.delete(  # type: ignore[misc]
                f"/api/v2/nodes/{nid}/docker/containers/{cid}?force=true"
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
        response = self._client.post("/api/v2/commands/", json={"items": [payload]})
        if response.status_code == 422:
            alt = self._client.post("/api/v2/commands/", json=payload)
            if alt.status_code in (200, 201, 207):
                response = alt
        item = self._unwrap_bulk(response, payload, id_field="id")
        iid = str(item["id"])
        self._cleanup.add(
            lambda iid=iid: self._client.delete(f"/api/v2/commands/{iid}")  # type: ignore[misc]
        )
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
        response = self._client.post("/api/v2/scripts/", json={"items": [payload]})
        if response.status_code == 422:
            alt = self._client.post("/api/v2/scripts/", json=payload)
            if alt.status_code in (200, 201, 207):
                response = alt
        item = self._unwrap_bulk(response, payload, id_field="id")
        iid = str(item["id"])
        self._cleanup.add(
            lambda iid=iid: self._client.delete(f"/api/v2/scripts/{iid}")  # type: ignore[misc]
        )
        return item

    def create_api_key(self, **overrides: object) -> UnvalidatedJsonObject:
        """Create a managed API key."""
        payload: dict[str, object] = {
            "name": self.unique_name("e2e-key"),
            "scope": "read-write",
        }
        payload.update(overrides)
        item = self._assert_created(
            self._client.post("/api/v2/api-keys/", json=payload)
        )
        iid = str(item["id"])
        self._cleanup.add(
            lambda iid=iid: self._client.delete(f"/api/v2/api-keys/{iid}")  # type: ignore[misc]
        )
        return item

    def create_schedule(
        self,
        script_id: str,
        node_ids: list[str],
        cron: str = "* * * * *",
    ) -> UnvalidatedJsonObject:
        """Create or replace a script schedule."""
        response = self._client.post(
            f"/api/v2/scripts/{script_id}/schedule",
            json={"cron": cron, "node_ids": node_ids},
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        self._cleanup.add(
            lambda sid=script_id: self._client.delete(  # type: ignore[misc]
                f"/api/v2/scripts/{sid}/schedule"
            )
        )
        return response.json()

    def trigger_schedule_now(self, script_id: str) -> None:
        """Immediately trigger a scheduled script via the E2E harness endpoint."""
        response = self._client.post(
            f"/api/v2/internal/e2e/scheduler/{script_id}/trigger-now"
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
