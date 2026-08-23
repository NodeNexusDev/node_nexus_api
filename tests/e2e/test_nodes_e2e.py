"""E2E tests for node CRUD, SSH operations, tags, search, metrics, cursor pagination."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx2 as httpx
import pytest

from app.schemas.common import encode_cursor
from tests.e2e.conftest import ServicePorts
from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


def test_crud_full_cycle(e2e_client: httpx.Client) -> None:
    # Create
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "e2e-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node = resp.json()
    node_id = node["id"]
    assert node["name"] == "e2e-node"
    assert node["status"] == "active"

    # Read
    resp = e2e_client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-node"

    # Read all — verify PaginatedResponse structure
    resp = e2e_client.get("/api/v1/nodes/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert data["total"] >= 1

    # Update
    resp = e2e_client.patch(
        f"/api/v1/nodes/{node_id}",
        json={"name": "e2e-node-updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-node-updated"

    # Delete
    resp = e2e_client.delete(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = e2e_client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 404


def test_create_with_credentials(
    e2e_client: httpx.Client, service_ports: ServicePorts
) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "ssh-node",
            "host": service_ports.ssh_host,
            "port": service_ports.ssh_port,
            "connection_type": "ssh",
            "username": "testuser",
            "password": "testpass",
        },
    )
    assert resp.status_code == 201
    node = resp.json()
    assert node["name"] == "ssh-node"
    assert node["username"] == "testuser"
    # Secrets must NOT be in response
    assert "password" not in node
    assert "ssh_key" not in node
    assert "passphrase" not in node


def test_create_with_passphrase(
    e2e_client: httpx.Client, service_ports: ServicePorts
) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "ssh-passphrase-node",
            "host": service_ports.ssh_host,
            "port": service_ports.ssh_port,
            "connection_type": "ssh",
            "username": "testuser",
            "ssh_key": (
                "-----BEGIN OPENSSH PRIVATE KEY-----\n"
                "fake\n"
                "-----END OPENSSH PRIVATE KEY-----"
            ),
            "passphrase": "my-secret-passphrase",
        },
    )
    assert resp.status_code == 201
    node = resp.json()
    assert node["name"] == "ssh-passphrase-node"
    # Secrets must NOT be in response
    assert "password" not in node
    assert "ssh_key" not in node
    assert "passphrase" not in node


# ---------------------------------------------------------------------------
# SSH key-based authentication
# ---------------------------------------------------------------------------


def test_ssh_key_auth_check(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Connect via unencrypted SSH key — /check returns active."""
    node = e2e_resources.create_ssh_key_node(encrypted=False)
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_ssh_key_auth_execute(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Execute a command via unencrypted SSH key."""
    node = e2e_resources.create_ssh_key_node(encrypted=False)
    resp = e2e_client.post(
        "/api/v1/commands/execute",
        json={"node_id": node['id'], "command": "echo e2e-key-works"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["stdout"].strip() == "e2e-key-works"
    assert result["exit_code"] == 0


def test_ssh_encrypted_key_auth_check(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Connect via encrypted SSH key + passphrase — /check returns active."""
    node = e2e_resources.create_ssh_key_node(encrypted=True)
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_ssh_encrypted_key_auth_execute(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Execute a command via encrypted SSH key + passphrase."""
    node = e2e_resources.create_ssh_key_node(encrypted=True)
    resp = e2e_client.post(
        "/api/v1/commands/execute",
        json={"node_id": node['id'], "command": "echo e2e-enc-key-works"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["stdout"].strip() == "e2e-enc-key-works"
    assert result["exit_code"] == 0


def test_ssh_encrypted_key_wrong_passphrase(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Encrypted key with wrong passphrase — /check returns unreachable."""
    node = e2e_resources.create_ssh_key_node(
        encrypted=True,
        passphrase="wrong-passphrase",
    )
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreachable"


def test_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={"name": "incomplete"},
    )
    assert resp.status_code == 422


def test_not_found_errors(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())

    resp = e2e_client.get(f"/api/v1/nodes/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.patch(
        f"/api/v1/nodes/{fake_id}",
        json={"name": "x"},
    )
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v1/nodes/{fake_id}")
    assert resp.status_code == 404


def test_ssh_check_connectivity(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-test")
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_ssh_execute_command(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-exec")
    resp = e2e_client.post(
        "/api/v1/commands/execute",
        json={"node_id": node['id'], "command": "echo e2e-works"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["stdout"].strip() == "e2e-works"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_ssh_execute_command_non_zero_exit(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-fail")
    resp = e2e_client.post(
        "/api/v1/commands/execute",
        json={"node_id": node['id'], "command": "exit 42"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["exit_code"] == 42


def test_ssh_execute_command_stderr(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-stderr")
    resp = e2e_client.post(
        "/api/v1/commands/execute",
        json={"node_id": node['id'], "command": "echo error-output >&2"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert "error-output" in result["stderr"]
    assert result["exit_code"] == 0


def test_ssh_check_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(f"/api/v1/nodes/{uuid4()}/check")
    assert resp.status_code == 404


def test_ssh_execute_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/commands/execute",
        json={"node_id": str(uuid4()), "command": "ls"},
    )
    assert resp.status_code == 404


def test_pagination_page2(e2e_client: httpx.Client) -> None:
    created: list[str] = []
    for i in range(3):
        resp = e2e_client.post(
            "/api/v1/nodes/",
            json={
                "name": f"page-test-{i}",
                "host": "10.0.0.1",
                "port": 22,
                "connection_type": "ssh",
            },
        )
        created.append(resp.json()["id"])

    resp = e2e_client.get("/api/v1/nodes/?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["size"] == 2

    for node_id in created:
        e2e_client.delete(f"/api/v1/nodes/{node_id}")


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------


def test_ssh_check_wrong_credentials(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Wrong credentials return 200 with status="unreachable".

    The /check endpoint always returns 200 — it reports connectivity
    status via the response body, not HTTP status codes.
    """
    node = e2e_resources.create_ssh_node(
        name="ssh-bad", username="testuser", password="wrongpass"
    )
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreachable"


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def test_partial_update(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "partial-orig",
            "host": "10.0.0.99",
            "port": 2222,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]
    original_host = resp.json()["host"]

    resp = e2e_client.patch(f"/api/v1/nodes/{node_id}", json={"name": "partial-new"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "partial-new"
    assert updated["host"] == original_host
    assert updated["port"] == 2222


# ---------------------------------------------------------------------------
# CORS preflight
# ---------------------------------------------------------------------------


def test_create_node_invalid_connection_type(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "bad-type",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "invalid",
        },
    )
    assert resp.status_code == 422


def test_create_node_valid_connection_types(e2e_client: httpx.Client) -> None:
    for ctype in ("ssh", "docker", "proxmox"):
        resp = e2e_client.post(
            "/api/v1/nodes/",
            json={
                "name": f"type-{ctype}",
                "host": "10.0.0.1",
                "port": 22,
                "connection_type": ctype,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["connection_type"] == ctype
        e2e_client.delete(f"/api/v1/nodes/{resp.json()['id']}")


# ---------------------------------------------------------------------------
# Command execute (requires SSH node)
# ---------------------------------------------------------------------------


def test_create_node_invalid_port(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "bad-port",
            "host": "10.0.0.1",
            "port": 99999,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 422


def test_create_node_port_zero(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "port-zero",
            "host": "10.0.0.1",
            "port": 0,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Duplicate name handling
# ---------------------------------------------------------------------------


def test_create_node_duplicate_name(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Node names are unique and duplicate creation is a conflict."""
    e2e_resources.create_node(name="dup-name")
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "dup-name",
            "host": "10.0.0.2",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Node tags CRUD
# ---------------------------------------------------------------------------


def test_node_create_with_tags(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "tagged-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
            "tags": ["prod", "web"],
        },
    )
    assert resp.status_code == 201
    node = resp.json()
    assert sorted(node["tags"]) == ["prod", "web"]

    # Read back
    resp = e2e_client.get(f"/api/v1/nodes/{node['id']}")
    assert resp.status_code == 200
    assert sorted(resp.json()["tags"]) == ["prod", "web"]

    e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_node_get_all_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="tag-a", tags=["alpha", "beta"])
    e2e_resources.create_node(name="tag-b", tags=["beta", "gamma"])

    resp = e2e_client.get("/api/v1/nodes/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert "alpha" in tags
    assert "beta" in tags
    assert "gamma" in tags


# ---------------------------------------------------------------------------
# Node filtering and search
# ---------------------------------------------------------------------------


def test_node_filter_by_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="filter-prod-web", tags=["prod", "web"])
    e2e_resources.create_node(name="filter-prod-db", tags=["prod", "db"])
    e2e_resources.create_node(name="filter-staging", tags=["staging"])

    resp = e2e_client.get("/api/v1/nodes/?tags=prod")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "filter-prod-web" in names
    assert "filter-prod-db" in names
    assert "filter-staging" not in names


def test_node_filter_by_multiple_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="multi-tag-1", tags=["prod", "web"])
    e2e_resources.create_node(name="multi-tag-2", tags=["prod", "db"])
    e2e_resources.create_node(name="multi-tag-3", tags=["prod"])

    resp = e2e_client.get("/api/v1/nodes/?tags=prod,web")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "multi-tag-1" in names
    assert "multi-tag-2" not in names  # has prod but not web


def test_node_search_by_name(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="search-web-1", host="10.0.0.1")
    e2e_resources.create_node(name="search-db-1", host="10.0.0.2")

    resp = e2e_client.get("/api/v1/nodes/?search=web")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "search-web-1" in names
    assert "search-db-1" not in names


def test_node_search_by_host(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="host-alpha", host="prod.example.com")
    e2e_resources.create_node(name="host-beta", host="staging.example.com")

    resp = e2e_client.get("/api/v1/nodes/?search=prod")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "host-alpha" in names
    assert "host-beta" not in names


def test_node_filter_by_tags_and_search(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(
        name="combo-web-prod", host="10.0.0.1", tags=["prod", "web"]
    )
    e2e_resources.create_node(
        name="combo-db-prod", host="10.0.0.2", tags=["prod", "db"]
    )
    e2e_resources.create_node(
        name="combo-web-staging",
        host="10.0.0.3",
        tags=["staging", "web"],
    )

    resp = e2e_client.get("/api/v1/nodes/?tags=prod&search=web")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "combo-web-prod" in names
    assert "combo-db-prod" not in names  # has prod but not web in name
    assert "combo-web-staging" not in names  # has web but not prod tag


def test_node_filter_empty_result(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="no-match", tags=["dev"])

    resp = e2e_client.get("/api/v1/nodes/?search=nonexistent")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Node bulk execute
# ---------------------------------------------------------------------------


def test_node_metrics(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """GET /nodes/{id}/metrics returns system metrics."""
    node = e2e_resources.create_ssh_node(name="metrics-node")
    resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "cpu" in data
    assert "memory" in data
    assert "disk" in data
    assert "uptime_since" in data
    assert data["cpu"]["usage_percent"] >= 0
    assert data["cpu"]["cores"] >= 1


def test_node_metrics_not_found(e2e_client: httpx.Client) -> None:
    """GET /nodes/{id}/metrics returns 404 for nonexistent node."""
    resp = e2e_client.get(f"/api/v1/nodes/{uuid4()}/metrics")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_cursor_first_page(e2e_client: httpx.Client) -> None:
    """First page without cursor returns nodes."""
    nodes = []
    for i in range(3):
        resp = e2e_client.post(
            "/api/v1/nodes/",
            json={
                "name": f"cursor-node-{i}",
                "host": f"10.0.0.{i}",
                "port": 22,
                "connection_type": "ssh",
            },
        )
        assert resp.status_code == 201
        nodes.append(resp.json())

    try:
        cursor = encode_cursor(datetime.now(UTC), uuid4())
        resp = e2e_client.get(f"/api/v1/nodes/?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "has_more" in data
        assert "next_cursor" in data
        assert len(data["items"]) <= 2
    finally:
        for node in nodes:
            e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_cursor_pagination(e2e_client: httpx.Client) -> None:
    """Cursor pagination returns next page without duplicates."""
    nodes = []
    for i in range(5):
        resp = e2e_client.post(
            "/api/v1/nodes/",
            json={
                "name": f"cursor-page-{i}",
                "host": f"10.0.1.{i}",
                "port": 22,
                "connection_type": "ssh",
            },
        )
        assert resp.status_code == 201
        nodes.append(resp.json())

    try:
        cursor = encode_cursor(datetime.now(UTC), uuid4())
        resp = e2e_client.get(f"/api/v1/nodes/?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        page1 = resp.json()
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        resp = e2e_client.get(f"/api/v1/nodes/?cursor={page1['next_cursor']}&limit=2")
        assert resp.status_code == 200
        page2 = resp.json()

        page1_ids = {n["id"] for n in page1["items"]}
        page2_ids = {n["id"] for n in page2["items"]}
        assert not page1_ids & page2_ids
    finally:
        for node in nodes:
            e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_cursor_invalid(e2e_client: httpx.Client) -> None:
    """Invalid cursor returns 422."""
    resp = e2e_client.get("/api/v1/nodes/?cursor=invalid-cursor!!!")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Config export/import
# ---------------------------------------------------------------------------
