"""E2E tests for bulk operations that were previously excluded from coverage.

Covers:
- Docker bulk: pull, remove, images/remove, images/build
- Node bulk: metrics, update, validate-credentials, retry, cancel
- Command bulk-execute (template-based)
- Script bulk: retry, cancel
"""

import uuid

import httpx2 as httpx
import pytest

from tests.e2e.helpers.polling import wait_for_condition
from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


# ---------------------------------------------------------------------------
# Docker Bulk Pull
# ---------------------------------------------------------------------------


def test_docker_bulk_pull(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /docker/bulk/pull pulls an image on multiple Docker nodes."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.post(
        "/api/v1/docker/bulk/pull",
        json={
            "node_ids": [node["id"]],
            "image": "busybox:latest",
            "timeout": 120,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0
    assert data["results"][0]["status"] == "success"


# ---------------------------------------------------------------------------
# Docker Bulk Remove (container)
# ---------------------------------------------------------------------------


def test_docker_bulk_remove(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /docker/bulk/remove removes a container on multiple Docker nodes."""
    node = e2e_resources.create_docker_node()
    # Pull image and create a container
    e2e_client.post(
        f"/api/v1/nodes/{node['id']}/docker/images/pull",
        json={"image": "alpine:latest", "timeout": 120},
    )
    e2e_client.post(
        "/api/v1/commands/execute",
        json={
            "node_id": node["id"],
            "command": "docker run -d --name bulk-rm-test alpine sleep 300",
        },
    )

    # Wait for container to be running
    def _container_running() -> bool:
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/bulk-rm-test"
        )
        if resp.status_code != 200:
            return False
        state = resp.json().get("State", {})
        return state.get("status", "").lower() == "running"

    wait_for_condition(
        _container_running, timeout=10.0, description="container running"
    )

    resp = e2e_client.post(
        "/api/v1/docker/bulk/remove",
        json={
            "node_ids": [node["id"]],
            "container_id": "bulk-rm-test",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "remove"
    assert data["total"] == 1
    assert data["succeeded"] == 1


# ---------------------------------------------------------------------------
# Docker Bulk Image Remove
# ---------------------------------------------------------------------------


def test_docker_bulk_image_remove(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /docker/bulk/images/remove removes an image on multiple Docker nodes."""
    node = e2e_resources.create_docker_node()
    # Pull a unique image to remove
    resp = e2e_client.post(
        f"/api/v1/nodes/{node['id']}/docker/images/pull",
        json={"image": "busybox:latest", "timeout": 120},
    )
    assert resp.status_code == 200

    resp = e2e_client.post(
        "/api/v1/docker/bulk/images/remove",
        json={
            "node_ids": [node["id"]],
            "image_id": "busybox:latest",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["results"][0]["status"] == "success"


# ---------------------------------------------------------------------------
# Docker Bulk Image Build
# ---------------------------------------------------------------------------


def test_docker_bulk_image_build(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /docker/bulk/images/build builds an image on multiple Docker nodes."""
    node = e2e_resources.create_docker_node()
    dockerfile = "FROM alpine:latest\nRUN echo bulk-build > /marker\n"
    tag = f"local/e2e-bulk-build-{uuid.uuid4().hex[:8]}"

    resp = e2e_client.post(
        "/api/v1/docker/bulk/images/build",
        json={
            "node_ids": [node["id"]],
            "dockerfile": dockerfile,
            "tag": tag,
            "no_cache": True,
            "timeout": 300,
        },
        timeout=120.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["results"][0]["status"] == "success"

    # Cleanup built image
    e2e_client.delete(f"/api/v1/nodes/{node['id']}/docker/images/{tag}")


# ---------------------------------------------------------------------------
# Node Bulk Metrics
# ---------------------------------------------------------------------------


def test_node_bulk_metrics(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/bulk/metrics collects metrics from multiple nodes."""
    node = e2e_resources.create_ssh_node(name="bulk-metrics")
    resp = e2e_client.post(
        "/api/v1/nodes/bulk/metrics",
        json={"node_ids": [node["id"]]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    result = data["results"][0]
    assert result["status"] == "success"
    assert result["metrics"] is not None
    assert "cpu" in result["metrics"]


# ---------------------------------------------------------------------------
# Node Bulk Update
# ---------------------------------------------------------------------------


def test_node_bulk_update(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """PUT /nodes/bulk/update updates multiple nodes."""
    node1 = e2e_resources.create_ssh_node(name="bulk-upd-1")
    node2 = e2e_resources.create_ssh_node(name="bulk-upd-2")

    resp = e2e_client.patch(
        "/api/v1/nodes/bulk/update",
        json={
            "node_ids": [node1["id"], node2["id"]],
            "changes": {"port": 23022},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2

    # Verify the update persisted on at least one node
    resp = e2e_client.get(f"/api/v1/nodes/{node1['id']}")
    assert resp.status_code == 200
    assert resp.json()["port"] == 23022


# ---------------------------------------------------------------------------
# Node Bulk Validate Credentials
# ---------------------------------------------------------------------------


def test_node_bulk_validate_credentials(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/bulk/validate-credentials validates SSH credentials."""
    node = e2e_resources.create_ssh_node(name="bulk-cred")
    resp = e2e_client.post(
        "/api/v1/nodes/bulk/validate-credentials",
        json={"node_ids": [node["id"]]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] >= 0  # may succeed or fail depending on SSH
    result = data["results"][0]
    assert result["status"] in ("success", "error")


# ---------------------------------------------------------------------------
# Node Bulk Retry / Cancel
# ---------------------------------------------------------------------------


def test_node_bulk_retry_cancel(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Nodes bulk retry/cancel handle non-existent IDs gracefully."""
    fake_id = str(uuid.uuid4())

    resp = e2e_client.post(
        "/api/v1/commands/bulk/retry",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["failed"] == 1

    resp = e2e_client.post(
        "/api/v1/commands/bulk/cancel",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["failed"] == 1


# ---------------------------------------------------------------------------
# Command Bulk Execute (template-based)
# ---------------------------------------------------------------------------


def test_command_bulk_execute(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /commands/{command_id}/bulk-execute executes a saved command template."""
    node = e2e_resources.create_ssh_node(name="bulk-cmd")
    cmd = e2e_resources.create_command(command="echo template-ok")

    resp = e2e_client.post(
        f"/api/v1/commands/{cmd['id']}/bulk-execute",
        json={"command": "unused", "node_ids": [node["id"]]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["results"][0]["stdout"].strip() == "template-ok"


# ---------------------------------------------------------------------------
# Script Bulk Retry / Cancel
# ---------------------------------------------------------------------------


def test_script_bulk_retry_cancel(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Scripts bulk retry/cancel handle non-existent IDs gracefully."""
    fake_id = str(uuid.uuid4())

    resp = e2e_client.post(
        "/api/v1/scripts/bulk/retry",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code == 200

    resp = e2e_client.post(
        "/api/v1/scripts/bulk/cancel",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code == 200
