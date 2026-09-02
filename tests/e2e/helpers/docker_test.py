"""Docker test helpers for E2E tests.

These helpers create and manage Docker containers/images via the HTTP API,
building on top of the existing e2e patterns (SSH exec for container run).
"""

import uuid

import httpx2 as httpx

from tests.e2e.helpers.polling import wait_for_condition


def ensure_image_pulled(
    e2e_client: httpx.Client,
    node_id: str,
    image: str = "alpine:3.20",
    timeout: int = 120,
) -> None:
    """Pull a Docker image on a node. No-op if already present.

    Uses the Docker pull API endpoint.  Assertion-free — callers
    decide what to check.
    """
    resp = e2e_client.post(
        f"/api/v2/nodes/{node_id}/docker/images/pull",
        json={"image": image, "timeout": timeout},
    )
    assert resp.status_code == 200, (
        f"Failed to pull image {image}: {resp.status_code} {resp.text}"
    )


def create_test_container(
    e2e_client: httpx.Client,
    node_id: str,
    image: str,
    command: str,
    name: str | None = None,
) -> str:
    """Run a container via SSH docker run and return container_id.

    The container is started via SSH exec (docker run -d) via
    bulk raw-executions.
    """
    container_name = name or f"e2e-ctr-{uuid.uuid4().hex[:8]}"
    docker_cmd = f"docker run -d --name {container_name} {image} {command}"
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"node_ids": [node_id], "commands": [docker_cmd]},
    )
    assert resp.status_code in (200, 207), (
        f"Failed to create container '{container_name}': {resp.status_code} {resp.text}"
    )
    data = resp.json()
    assert data["succeeded"] == 1, f"Container start failed: {data}"
    return container_name


def remove_test_container(
    e2e_client: httpx.Client,
    node_id: str,
    container_id: str,
    *,
    force: bool = True,
) -> None:
    """Remove a container via the Docker HTTP API."""
    force_param = "?force=true" if force else ""
    resp = e2e_client.delete(
        f"/api/v2/nodes/{node_id}/docker/containers/{container_id}{force_param}"
    )
    # 204 = success, 404 = already gone — both acceptable
    assert resp.status_code in (204, 404), (
        f"Failed to remove container '{container_id}': {resp.status_code} {resp.text}"
    )


def wait_for_container_running(
    e2e_client: httpx.Client,
    node_id: str,
    container_id: str,
    timeout: float = 15.0,
) -> None:
    """Wait until container State.status == running."""

    def _is_running() -> bool:
        resp = e2e_client.get(
            f"/api/v2/nodes/{node_id}/docker/containers/{container_id}"
        )
        if resp.status_code != 200:
            return False
        try:
            data = resp.json()
            if not isinstance(data, dict):
                return False
            state = data.get("State")
            if not isinstance(state, dict):
                return False
            status = state.get("status")
            if status == "running":
                return True
            return False
        except Exception:
            return False

    wait_for_condition(
        _is_running, timeout=timeout, description=f"{container_id} running"
    )
