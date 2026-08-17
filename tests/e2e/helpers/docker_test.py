"""Docker test helpers for E2E tests.

These helpers create and manage Docker containers/images via the HTTP API,
building on top of the existing e2e patterns (SSH exec for container run).
"""

import uuid

import httpx2 as httpx


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
        f"/api/v1/nodes/{node_id}/docker/images/pull",
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

    The container is started via SSH exec (docker run -d) since the
    HTTP API does not expose a dedicated container-create endpoint yet.

    Returns the container name/ID as passed or auto-generated.
    """
    container_name = name or f"e2e-ctr-{uuid.uuid4().hex[:8]}"
    docker_cmd = f"docker run -d --name {container_name} {image} {command}"
    resp = e2e_client.post(
        f"/api/v1/nodes/{node_id}/execute",
        json={"command": docker_cmd},
    )
    assert resp.status_code == 200, (
        f"Failed to create container '{container_name}': {resp.status_code} {resp.text}"
    )
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
        f"/api/v1/nodes/{node_id}/docker/containers/{container_id}{force_param}"
    )
    # 204 = success, 404 = already gone — both acceptable
    assert resp.status_code in (204, 404), (
        f"Failed to remove container '{container_id}': {resp.status_code} {resp.text}"
    )
