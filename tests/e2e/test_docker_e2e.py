"""E2E tests for Docker operations via HTTP API.

These tests focus on API validation and error handling.
They do NOT require a real Docker daemon - they test the API layer only.
"""

import uuid
from collections.abc import AsyncIterator

import httpx2 as httpx
import pytest

from tests.e2e.conftest import ServicePorts
from tests.e2e.settings import DEFAULT_TIMEOUT, MASTER_API_KEY


@pytest.fixture
async def client(service_ports: ServicePorts) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url=f"http://{service_ports.api_host}:{service_ports.api_port}",
        headers={"X-API-Key": MASTER_API_KEY},
        timeout=DEFAULT_TIMEOUT,
    ) as c:
        yield c


@pytest.mark.docker
class TestDockerAPIValidation:
    """Test Docker API validation without requiring Docker daemon."""

    async def test_create_docker_node(self, client: httpx.AsyncClient) -> None:
        """Test creating a Docker node."""
        node_data = {
            "name": f"docker-test-{uuid.uuid4().hex[:8]}",
            "host": "localhost",
            "port": 22,
            "connection_type": "ssh",
            "has_docker": True,
            "username": "testuser",
            "password": "testpass",
        }
        response = await client.post("/api/v1/nodes/", json=node_data)
        assert response.status_code == 201
        data = response.json()
        assert data["connection_type"] == "ssh"
        assert data["has_docker"] is True
        assert data["name"] == node_data["name"]
        node_id = data["id"]

        # Cleanup
        await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_invalid_container_id_rejected(
        self, client: httpx.AsyncClient
    ) -> None:
        """Test that invalid container ID is rejected at API level."""
        # Create node
        node_data = {
            "name": f"docker-test-{uuid.uuid4().hex[:8]}",
            "host": "localhost",
            "port": 22,
            "connection_type": "ssh",
            "has_docker": True,
        }
        create_response = await client.post("/api/v1/nodes/", json=node_data)
        node_id = create_response.json()["id"]

        try:
            # Try to get container with invalid ID (contains pipe - command injection)
            response = await client.get(
                f"/api/v1/nodes/{node_id}/docker/containers/invalid|id"
            )
            assert response.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_invalid_image_name_rejected(self, client: httpx.AsyncClient) -> None:
        """Test that invalid image name is rejected at API level."""
        # Create node
        node_data = {
            "name": f"docker-test-{uuid.uuid4().hex[:8]}",
            "host": "localhost",
            "port": 22,
            "connection_type": "ssh",
            "has_docker": True,
        }
        create_response = await client.post("/api/v1/nodes/", json=node_data)
        node_id = create_response.json()["id"]

        try:
            # Try to pull image with invalid name (semicolon = injection attempt)
            response = await client.post(
                f"/api/v1/nodes/{node_id}/docker/images/pull",
                json={"image": "nginx;rm -rf /"},
            )
            assert response.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_docker_node_validation(self, client: httpx.AsyncClient) -> None:
        """Test that non-docker nodes are rejected for Docker operations."""
        # Create SSH node
        ssh_node_data = {
            "name": f"ssh-test-{uuid.uuid4().hex[:8]}",
            "host": "localhost",
            "port": 22,
            "connection_type": "ssh",
            "username": "testuser",
            "password": "testpass",
        }
        create_response = await client.post("/api/v1/nodes/", json=ssh_node_data)
        node_id = create_response.json()["id"]

        try:
            # Try Docker operations on SSH node - should return 502
            response = await client.get(f"/api/v1/nodes/{node_id}/docker/containers")
            assert response.status_code == 502
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_nonexistent_node_returns_404(
        self, client: httpx.AsyncClient
    ) -> None:
        """Test that nonexistent node returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/nodes/{fake_id}/docker/containers")
        assert response.status_code == 404

    async def test_docker_endpoints_exist(self, client: httpx.AsyncClient) -> None:
        """Test that all Docker endpoints are registered."""
        # Create node
        node_data = {
            "name": f"docker-test-{uuid.uuid4().hex[:8]}",
            "host": "localhost",
            "port": 22,
            "connection_type": "ssh",
            "has_docker": True,
        }
        create_response = await client.post("/api/v1/nodes/", json=node_data)
        node_id = create_response.json()["id"]

        try:
            # Check that endpoints exist (will return 502 because no Docker daemon,
            # but not 404 or 405)
            endpoints = [
                f"/api/v1/nodes/{node_id}/docker/containers",
                f"/api/v1/nodes/{node_id}/docker/images",
                f"/api/v1/nodes/{node_id}/docker/networks",
                f"/api/v1/nodes/{node_id}/docker/volumes",
            ]
            for endpoint in endpoints:
                response = await client.get(endpoint)
                # Should be 200, 502 (Docker error), or 503 (connection failed)
                assert response.status_code in (200, 502, 503), (
                    f"Endpoint {endpoint} returned {response.status_code}"
                )
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_exec_empty_command_rejected(self, client: httpx.AsyncClient) -> None:
        """Test that empty command is rejected."""
        # Create node
        node_data = {
            "name": f"docker-test-{uuid.uuid4().hex[:8]}",
            "host": "localhost",
            "port": 22,
            "connection_type": "ssh",
            "has_docker": True,
        }
        create_response = await client.post("/api/v1/nodes/", json=node_data)
        node_id = create_response.json()["id"]

        try:
            # Try to exec with empty command
            response = await client.post(
                f"/api/v1/nodes/{node_id}/docker/containers/abc123/exec",
                json={"command": ""},
            )
            assert response.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_exec_long_command_rejected(self, client: httpx.AsyncClient) -> None:
        """Test that too long command is rejected."""
        # Create node
        node_data = {
            "name": f"docker-test-{uuid.uuid4().hex[:8]}",
            "host": "localhost",
            "port": 22,
            "connection_type": "ssh",
            "has_docker": True,
        }
        create_response = await client.post("/api/v1/nodes/", json=node_data)
        node_id = create_response.json()["id"]

        try:
            # Try to exec with command longer than 4096 chars
            long_command = "a" * 4097
            response = await client.post(
                f"/api/v1/nodes/{node_id}/docker/containers/abc123/exec",
                json={"command": long_command},
            )
            assert response.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")


def _make_docker_node_data() -> dict[str, object]:
    return {
        "name": f"docker-test-{uuid.uuid4().hex[:8]}",
        "host": "localhost",
        "port": 22,
        "connection_type": "ssh",
        "has_docker": True,
        "username": "testuser",
        "password": "testpass",
    }


def _make_ssh_node_data() -> dict[str, object]:
    return {
        "name": f"ssh-test-{uuid.uuid4().hex[:8]}",
        "host": "localhost",
        "port": 22,
        "connection_type": "ssh",
        "username": "testuser",
        "password": "testpass",
    }


CONTAINER_BASE = "/api/v1/nodes/{node_id}/docker/containers"
FAKE_CONTAINER_ID = "abc123def456"
INJECT_CONTAINER_ID = "invalid|id"


@pytest.mark.docker
class TestDockerContainerLifecycle:
    """Test Docker container lifecycle endpoints (start/stop/restart/remove/logs/stats).

    No real Docker daemon — verifies API validation and error handling only.
    """

    # --- POST .../start ---

    async def test_start_invalid_container_id(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{INJECT_CONTAINER_ID}/start"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_start_nonexistent_node(self, client: httpx.AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"{CONTAINER_BASE.format(node_id=fake_id)}/{FAKE_CONTAINER_ID}/start"
        )
        assert resp.status_code == 404

    async def test_start_docker_node_no_daemon(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/start"
            )
            assert resp.status_code in (502, 503)
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    # --- POST .../stop ---

    async def test_stop_invalid_container_id(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{INJECT_CONTAINER_ID}/stop"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_stop_nonexistent_node(self, client: httpx.AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"{CONTAINER_BASE.format(node_id=fake_id)}/{FAKE_CONTAINER_ID}/stop"
        )
        assert resp.status_code == 404

    async def test_stop_docker_node_no_daemon(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/stop"
            )
            assert resp.status_code in (502, 503)
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_stop_invalid_timeout(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/stop?timeout=0"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    # --- POST .../restart ---

    async def test_restart_invalid_container_id(
        self, client: httpx.AsyncClient
    ) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{INJECT_CONTAINER_ID}/restart"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_restart_nonexistent_node(self, client: httpx.AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"{CONTAINER_BASE.format(node_id=fake_id)}/{FAKE_CONTAINER_ID}/restart"
        )
        assert resp.status_code == 404

    async def test_restart_docker_node_no_daemon(
        self, client: httpx.AsyncClient
    ) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/restart"
            )
            assert resp.status_code in (502, 503)
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_restart_invalid_timeout(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.post(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/restart?timeout=0"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    # --- DELETE .../ ---

    async def test_remove_invalid_container_id(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.delete(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{INJECT_CONTAINER_ID}"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_remove_nonexistent_node(self, client: httpx.AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.delete(
            f"{CONTAINER_BASE.format(node_id=fake_id)}/{FAKE_CONTAINER_ID}"
        )
        assert resp.status_code == 404

    async def test_remove_docker_node_no_daemon(
        self, client: httpx.AsyncClient
    ) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.delete(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}"
            )
            assert resp.status_code in (502, 503)
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_remove_wrong_node_type(self, client: httpx.AsyncClient) -> None:
        node_data = _make_ssh_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.delete(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}"
            )
            assert resp.status_code == 502
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    # --- GET .../logs ---

    async def test_logs_invalid_container_id(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.get(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{INJECT_CONTAINER_ID}/logs"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_logs_nonexistent_node(self, client: httpx.AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"{CONTAINER_BASE.format(node_id=fake_id)}/{FAKE_CONTAINER_ID}/logs"
        )
        assert resp.status_code == 404

    async def test_logs_docker_node_no_daemon(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.get(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/logs"
            )
            assert resp.status_code in (502, 503)
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_logs_invalid_tail(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.get(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/logs?tail=10001"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    # --- GET .../stats ---

    async def test_stats_invalid_container_id(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.get(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{INJECT_CONTAINER_ID}/stats"
            )
            assert resp.status_code == 422
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")

    async def test_stats_nonexistent_node(self, client: httpx.AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"{CONTAINER_BASE.format(node_id=fake_id)}/{FAKE_CONTAINER_ID}/stats"
        )
        assert resp.status_code == 404

    async def test_stats_docker_node_no_daemon(self, client: httpx.AsyncClient) -> None:
        node_data = _make_docker_node_data()
        node_id = (await client.post("/api/v1/nodes/", json=node_data)).json()["id"]
        try:
            resp = await client.get(
                f"{CONTAINER_BASE.format(node_id=node_id)}/{FAKE_CONTAINER_ID}/stats"
            )
            assert resp.status_code in (502, 503)
        finally:
            await client.delete(f"/api/v1/nodes/{node_id}")


# ---------------------------------------------------------------------------
# Bulk by tags (A.6) — requires Docker infrastructure
# ---------------------------------------------------------------------------


@pytest.mark.docker
class TestDockerBulkByTags:
    """Bulk Docker operations resolved by node tags."""

    @staticmethod
    def _make_docker_node_data(tags: list[str]) -> dict[str, object]:
        unique = uuid.uuid4().hex[:8]
        return {
            "name": f"docker-bulk-tag-{unique}",
            "host": "ssh-server",
            "port": 2222,
            "connection_type": "ssh",
            "has_docker": True,
            "username": "testuser",
            "password": "testpass",
            "docker_host": "tcp://dind:2375",
            "tags": tags,
        }

    async def _pull_alpine(self, client: httpx.AsyncClient, node_id: str) -> None:
        resp = await client.post(
            f"/api/v1/nodes/{node_id}/docker/images/pull",
            json={"image": "alpine:latest", "timeout": 120},
        )
        assert resp.status_code == 200

    async def test_docker_bulk_by_tags(self, client: httpx.AsyncClient) -> None:
        """Create a tagged Docker node → bulk start by tag."""
        node_data = self._make_docker_node_data(["zone-a", "env-e2e"])
        node = (await client.post("/api/v1/nodes/", json=node_data)).json()
        container_name = f"bulk-tag-ctr-{uuid.uuid4().hex[:8]}"
        try:
            await self._pull_alpine(client, node["id"])
            # Run a container via SSH exec so we can bulk-start it
            run_cmd = f"docker run -d --name {container_name} alpine sleep 300"
            resp = await client.post(
                "/api/v1/commands/execute",
                json={"node_id": node["id"], "command": run_cmd},
            )
            assert resp.status_code == 200
            # Stop it first
            await client.post(
                f"/api/v1/nodes/{node['id']}/docker/containers/{container_name}/stop"
            )

            resp = await client.post(
                "/api/v1/docker/bulk/start",
                json={
                    "node_tags": ["env-e2e"],
                    "container_id": container_name,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["action"] == "start"
            assert data["total"] == 1
            assert data["succeeded"] == 1
        finally:
            await client.delete(
                f"/api/v1/nodes/{node['id']}/docker/containers/{container_name}?force=true"
            )
            await client.delete(f"/api/v1/nodes/{node['id']}")

    async def test_docker_bulk_mixed_ids_and_tags(
        self, client: httpx.AsyncClient
    ) -> None:
        """Both node_ids and node_tags provided → deduplicate."""
        node_data = self._make_docker_node_data(["zone-a", "env-e2e"])
        node = (await client.post("/api/v1/nodes/", json=node_data)).json()
        container_name = f"bulk-mixed-ctr-{uuid.uuid4().hex[:8]}"
        try:
            await self._pull_alpine(client, node["id"])
            cmd = f"docker run -d --name {container_name} alpine sleep 300"
            await client.post(
                "/api/v1/commands/execute",
                json={"node_id": node["id"], "command": cmd},
            )
            await client.post(
                f"/api/v1/nodes/{node['id']}/docker/containers/{container_name}/stop"
            )

            resp = await client.post(
                "/api/v1/docker/bulk/start",
                json={
                    "node_ids": [node["id"]],
                    "node_tags": ["env-e2e"],
                    "container_id": container_name,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            # Deduplicated to exactly one node
            assert data["total"] == 1
            assert data["succeeded"] == 1
        finally:
            await client.delete(
                f"/api/v1/nodes/{node['id']}/docker/containers/{container_name}?force=true"
            )
            await client.delete(f"/api/v1/nodes/{node['id']}")

    async def test_docker_bulk_no_targets_validation_error(
        self, client: httpx.AsyncClient
    ) -> None:
        """Empty node_ids and node_tags → 422."""
        resp = await client.post(
            "/api/v1/docker/bulk/start",
            json={"container_id": "any-ctr"},
        )
        assert resp.status_code == 422
