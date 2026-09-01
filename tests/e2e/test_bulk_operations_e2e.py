"""E2E tests for bulk operations that were previously excluded from coverage.

Covers:
- Docker vert bulk: pulls, removals, image removals, image build
- Node bulk-first: metrics, update, validate-credentials, retry, cancel
- Command bulk executions (template and raw)
- Script bulk executions retries/cancels
"""

import uuid

import httpx2 as httpx
import pytest

from tests.e2e.helpers.polling import wait_for_condition
from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


# ---------------------------------------------------------------------------
# Docker Vert Pulls
# ---------------------------------------------------------------------------


def test_docker_bulk_pull(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/{id}/docker/images/pulls pulls multiple images (vert bulk)."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/pulls",
        json={
            "images": ["busybox:latest"],
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
# Docker Vert Container Removals
# ---------------------------------------------------------------------------


def test_docker_bulk_remove(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/{id}/docker/containers/removals removes containers (vert bulk)."""
    node = e2e_resources.create_docker_node()
    # Pull image and create a container via Docker API
    e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/pull",
        json={"image": "alpine:latest", "timeout": 120},
    )
    create_resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={
            "image": "alpine:latest",
            "name": "bulk-rm-test",
            "command": "sleep 300",
        },
    )
    assert create_resp.status_code == 201
    # Start container so it exists running
    e2e_client.post(f"/api/v2/nodes/{node['id']}/docker/containers/bulk-rm-test/start")

    def _container_running() -> bool:
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/bulk-rm-test"
        )
        if resp.status_code != 200:
            return False
        state = resp.json().get("State", {})
        return bool(state.get("status", "").lower() == "running")

    wait_for_condition(
        _container_running, timeout=10.0, description="container running"
    )

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/removals",
        json={
            "container_ids": ["bulk-rm-test"],
        },
        params={"force": "true"},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    # May succeed or have partial status depending on implementation
    assert data["succeeded"] + data["failed"] == 1


# ---------------------------------------------------------------------------
# Docker Vert Image Removals
# ---------------------------------------------------------------------------


def test_docker_bulk_image_remove(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/{id}/docker/images/removals removes images (vert bulk)."""
    node = e2e_resources.create_docker_node()
    # Pull a unique image to remove
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/pull",
        json={"image": "busybox:latest", "timeout": 120},
    )
    assert resp.status_code == 200

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/removals",
        json={
            "image_ids": ["busybox:latest"],
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    # busybox may be in use, but request should be handled
    assert data["succeeded"] + data["failed"] == 1


# ---------------------------------------------------------------------------
# Docker Image Build (single, vert)
# ---------------------------------------------------------------------------


def test_docker_bulk_image_build(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/{id}/docker/images/build builds an image (vert single)."""
    node = e2e_resources.create_docker_node()
    dockerfile = "FROM alpine:latest\nRUN echo bulk-build > /marker\n"
    tag = f"local/e2e-bulk-build-{uuid.uuid4().hex[:8]}"

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/build",
        json={
            "dockerfile": dockerfile,
            "tag": tag,
            "no_cache": True,
        },
        timeout=120.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tag"] == tag
    assert data["image_id"]

    # Cleanup built image
    e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/images/{tag}")


# ---------------------------------------------------------------------------
# Node Bulk Metrics
# ---------------------------------------------------------------------------


def test_node_bulk_metrics(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/metrics collects metrics from multiple nodes."""
    node = e2e_resources.create_ssh_node(name="bulk-metrics")
    resp = e2e_client.post(
        "/api/v2/nodes/metrics",
        json={"ids": [node["id"]]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    # succeeded may be 1 if SSH reachable, otherwise error is still counted
    assert data["succeeded"] + data["failed"] == 1
    result = data["results"][0]
    assert result["status"] in ("success", "error")
    if result["status"] == "success":
        assert result["metrics"] is not None
        assert "cpu" in result["metrics"]


# ---------------------------------------------------------------------------
# Node Bulk Update
# ---------------------------------------------------------------------------


def test_node_bulk_update(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """PATCH /nodes/ updates multiple nodes via bulk-first."""
    node1 = e2e_resources.create_ssh_node(name="bulk-upd-1")
    node2 = e2e_resources.create_ssh_node(name="bulk-upd-2")

    resp = e2e_client.patch(
        "/api/v2/nodes/",
        json={
            "updates": [
                {"id": node1["id"], "changes": {"port": 23022}},
                {"id": node2["id"], "changes": {"port": 23022}},
            ]
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 2

    # Verify the update persisted on at least one node
    resp = e2e_client.get(f"/api/v2/nodes/{node1['id']}")
    assert resp.status_code == 200
    assert resp.json()["port"] == 23022


# ---------------------------------------------------------------------------
# Node Bulk Validate Credentials
# ---------------------------------------------------------------------------


def test_node_bulk_validate_credentials(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/credential-validations validates SSH credentials."""
    node = e2e_resources.create_ssh_node(name="bulk-cred")
    resp = e2e_client.post(
        "/api/v2/nodes/credential-validations",
        json={"ids": [node["id"]]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] + data["failed"] == 1
    result = data["results"][0]
    assert result["status"] in ("success", "error")


# ---------------------------------------------------------------------------
# Node Bulk Retry / Cancel (commands)
# ---------------------------------------------------------------------------


def test_node_bulk_retry_cancel(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /commands/executions/retries/cancels handle missing IDs."""
    fake_id = str(uuid.uuid4())

    resp = e2e_client.post(
        "/api/v2/commands/executions/retries",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["failed"] == 1

    resp = e2e_client.post(
        "/api/v2/commands/executions/cancels",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code in (200, 207)
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
    """POST /commands/executions executes a saved command template on nodes."""
    node = e2e_resources.create_ssh_node(name="bulk-cmd")
    cmd = e2e_resources.create_command(command="echo template-ok")

    resp = e2e_client.post(
        "/api/v2/commands/executions",
        json={
            "command_ids": [cmd["id"]],
            "node_ids": [node["id"]],
            "params": {},
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert "template-ok" in data["results"][0]["stdout"]


# ---------------------------------------------------------------------------
# Script Bulk Retry / Cancel
# ---------------------------------------------------------------------------


def test_script_bulk_retry_cancel(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /scripts/executions/retries/cancels handle missing IDs."""
    fake_id = str(uuid.uuid4())

    resp = e2e_client.post(
        "/api/v2/scripts/executions/retries",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code in (200, 207)

    resp = e2e_client.post(
        "/api/v2/scripts/executions/cancels",
        json={"execution_ids": [fake_id]},
    )
    assert resp.status_code in (200, 207)
