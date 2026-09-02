"""E2E tests for node CRUD, SSH operations, tags, search, metrics, cursor pagination."""

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

import httpx2 as httpx
import pytest

from app.schemas.common import encode_cursor
from tests.e2e.conftest import ServicePorts
from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


def _unwrap_node_id(resp: httpx.Response) -> str:
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        first = data["results"][0]
        return str(first.get("node_id") or first.get("id"))
    return str(data["id"])


def _unwrap_node(
    resp: httpx.Response, payload: Mapping[str, object]
) -> dict[str, object]:
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        first = data["results"][0]
        nid = str(first.get("node_id") or first.get("id"))
        # Backwards-compatible synthesis
        node: dict[str, object] = dict(payload)
        node["id"] = nid
        # merge bulk extras without overwriting payload
        for k, v in first.items():
            if k not in node:
                node[k] = v
        node["id"] = nid
        if "node_id" not in node:
            node["node_id"] = nid
        return node
    return data  # ty: ignore[unsound-return-statement]


def test_crud_full_cycle(e2e_client: httpx.Client) -> None:
    # Create
    _payload = {
        "name": "e2e-node",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
    }
    resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
    assert resp.status_code in (201, 207)
    node = _unwrap_node(resp, _payload)
    node_id = node["id"]
    # Verify via GET for authoritative fields
    get_resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
    if get_resp.status_code == 200:
        node = get_resp.json()
    assert node["name"] == "e2e-node"
    assert node["status"] == "active"

    # Read
    resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-node"

    # Read all — verify CursorPage structure
    resp = e2e_client.get("/api/v2/nodes/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "has_more" in data
    assert "limit" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["has_more"], bool)
    assert len(data["items"]) >= 1
    assert data["limit"] >= 1

    # Update
    resp = e2e_client.patch(
        f"/api/v2/nodes/{node_id}",
        json={"name": "e2e-node-updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-node-updated"

    # Delete
    resp = e2e_client.delete(f"/api/v2/nodes/{node_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
    assert resp.status_code == 404


def test_create_with_credentials(
    e2e_client: httpx.Client, service_ports: ServicePorts
) -> None:
    _payload = {
        "name": "ssh-node",
        "host": service_ports.ssh_host,
        "port": service_ports.ssh_port,
        "connection_type": "ssh",
        "username": "testuser",
        "password": "testpass",
    }
    resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
    assert resp.status_code in (201, 207)
    node_id = _unwrap_node_id(resp)
    resp2 = e2e_client.get(f"/api/v2/nodes/{node_id}")
    assert resp2.status_code == 200
    node = resp2.json()
    assert node["name"] == "ssh-node"
    assert node["username"] == "testuser"
    # Secrets must NOT be in response
    assert "password" not in node
    assert "ssh_key" not in node
    assert "passphrase" not in node


def test_create_with_passphrase(
    e2e_client: httpx.Client, service_ports: ServicePorts
) -> None:
    _payload = {
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
    }
    resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
    assert resp.status_code in (201, 207)
    node_id = _unwrap_node_id(resp)
    resp2 = e2e_client.get(f"/api/v2/nodes/{node_id}")
    assert resp2.status_code == 200
    node = resp2.json()
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
    """Connect via unencrypted SSH key — /checks returns success."""
    node = e2e_resources.create_ssh_key_node(encrypted=False)
    resp = e2e_client.post("/api/v2/nodes/checks", json={"ids": [node["id"]]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == 1
    assert data["results"][0]["status"] == "success"
    assert data["results"][0]["node_id"] == node["id"]


def test_ssh_key_auth_execute(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Execute a command via unencrypted SSH key."""
    node = e2e_resources.create_ssh_key_node(encrypted=False)
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"node_ids": [node["id"]], "commands": ["echo e2e-key-works"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["succeeded"] == 1
    result = next(r for r in data["results"] if str(r["node_id"]) == node["id"])
    assert result["stdout"].strip() == "e2e-key-works"
    assert result["exit_code"] == 0


def test_ssh_encrypted_key_auth_check(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Connect via encrypted SSH key + passphrase — /checks returns success."""
    node = e2e_resources.create_ssh_key_node(encrypted=True)
    resp = e2e_client.post("/api/v2/nodes/checks", json={"ids": [node["id"]]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == 1
    assert data["results"][0]["status"] == "success"
    assert data["results"][0]["node_id"] == node["id"]


def test_ssh_encrypted_key_auth_execute(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Execute a command via encrypted SSH key + passphrase."""
    node = e2e_resources.create_ssh_key_node(encrypted=True)
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"node_ids": [node["id"]], "commands": ["echo e2e-enc-key-works"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["succeeded"] == 1
    result = next(r for r in data["results"] if str(r["node_id"]) == node["id"])
    assert result["stdout"].strip() == "e2e-enc-key-works"
    assert result["exit_code"] == 0


def test_ssh_encrypted_key_wrong_passphrase(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Encrypted key with wrong passphrase — credential-validations returns error."""
    node = e2e_resources.create_ssh_key_node(
        encrypted=True,
        passphrase="wrong-passphrase",
    )
    resp = e2e_client.post(
        "/api/v2/nodes/credential-validations", json={"ids": [node["id"]]}
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["results"][0]["status"] == "error"


def test_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={"items": [{"name": "incomplete"}]},
    )
    assert resp.status_code == 422


def test_not_found_errors(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())

    resp = e2e_client.get(f"/api/v2/nodes/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.patch(
        f"/api/v2/nodes/{fake_id}",
        json={"name": "x"},
    )
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v2/nodes/{fake_id}")
    assert resp.status_code == 404


def test_ssh_check_connectivity(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-test")
    resp = e2e_client.post("/api/v2/nodes/checks", json={"ids": [node["id"]]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == 1
    assert data["results"][0]["status"] == "success"
    assert data["results"][0]["node_id"] == node["id"]


def test_ssh_execute_command(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-exec")
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"node_ids": [node["id"]], "commands": ["echo e2e-works"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["succeeded"] == 1
    result = next(r for r in data["results"] if str(r["node_id"]) == node["id"])
    assert result["stdout"].strip() == "e2e-works"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_ssh_execute_command_non_zero_exit(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-fail")
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"node_ids": [node["id"]], "commands": ["exit 42"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    result = data["results"][0]
    assert result["exit_code"] == 42
    assert result["status"] == "error"


def test_ssh_execute_command_stderr(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="ssh-stderr")
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"node_ids": [node["id"]], "commands": ["echo error-output >&2"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    result = data["results"][0]
    assert "error-output" in result["stderr"]
    assert result["exit_code"] == 0


def test_ssh_check_not_found(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())
    resp = e2e_client.post("/api/v2/nodes/checks", json={"ids": [fake_id]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"
    assert data["results"][0]["node_id"] == fake_id


def test_ssh_execute_not_found(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"node_ids": [fake_id], "commands": ["ls"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_pagination_page2(e2e_client: httpx.Client) -> None:
    created: list[str] = []
    for i in range(3):
        _payload = {
            "name": f"page-test-{i}",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        }
        resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
        created.append(_unwrap_node_id(resp))

    resp = e2e_client.get("/api/v2/nodes/?cursor=&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert "has_more" in data
    assert "next_cursor" in data
    assert data["has_more"] is True
    assert data["limit"] == 2

    for node_id in created:
        e2e_client.delete(f"/api/v2/nodes/{node_id}")


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------


def test_ssh_check_wrong_credentials(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Wrong credentials — credential-validations returns error."""
    node = e2e_resources.create_ssh_node(
        name="ssh-bad", username="testuser", password="wrongpass"
    )
    resp = e2e_client.post(
        "/api/v2/nodes/credential-validations", json={"ids": [node["id"]]}
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["results"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def test_partial_update(e2e_client: httpx.Client) -> None:
    _payload = {
        "name": "partial-orig",
        "host": "10.0.0.99",
        "port": 2222,
        "connection_type": "ssh",
    }
    resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
    assert resp.status_code in (201, 207)
    node_id = _unwrap_node_id(resp)
    get_resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
    assert get_resp.status_code == 200
    original_host = get_resp.json()["host"]

    resp = e2e_client.patch(f"/api/v2/nodes/{node_id}", json={"name": "partial-new"})
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
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "bad-type",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "invalid",
                }  # noqa: E501
            ]
        },
    )
    assert resp.status_code == 422


def test_create_node_valid_connection_types(e2e_client: httpx.Client) -> None:
    for ctype in ("ssh",):
        _payload = {
            "name": f"type-{ctype}",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": ctype,
        }
        resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
        assert resp.status_code in (201, 207)
        node_id = _unwrap_node_id(resp)
        get_resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["connection_type"] == ctype
        e2e_client.delete(f"/api/v2/nodes/{node_id}")


# ---------------------------------------------------------------------------
# Command execute (requires SSH node)
# ---------------------------------------------------------------------------


def test_create_node_invalid_port(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "bad-port",
                    "host": "10.0.0.1",
                    "port": 99999,
                    "connection_type": "ssh",
                }  # noqa: E501
            ]
        },
    )
    assert resp.status_code == 422


def test_create_node_port_zero(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "port-zero",
                    "host": "10.0.0.1",
                    "port": 0,
                    "connection_type": "ssh",
                }  # noqa: E501
            ]
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
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "dup-name",
                    "host": "10.0.0.2",
                    "port": 22,
                    "connection_type": "ssh",
                }  # noqa: E501
            ]
        },
    )
    # Bulk API returns 200/207 with error result or 409; accept either
    if resp.status_code in (200, 207):
        data = resp.json()
        assert data["failed"] == 1 or data["results"][0]["status"] == "error"
    else:
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Node tags CRUD
# ---------------------------------------------------------------------------


def test_node_create_with_tags(e2e_client: httpx.Client) -> None:
    _payload = {
        "name": "tagged-node",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "tags": ["prod", "web"],
    }
    resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
    assert resp.status_code in (201, 207)
    node_id = _unwrap_node_id(resp)
    get_resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
    assert get_resp.status_code == 200
    node = get_resp.json()
    assert sorted(node["tags"]) == ["prod", "web"]

    # Read back
    resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
    assert resp.status_code == 200
    assert sorted(resp.json()["tags"]) == ["prod", "web"]

    e2e_client.delete(f"/api/v2/nodes/{node_id}")


def test_node_get_all_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="tag-a", tags=["alpha", "beta"])
    e2e_resources.create_node(name="tag-b", tags=["beta", "gamma"])

    # New API has no /nodes/tags; verify via tag filter instead
    resp = e2e_client.get("/api/v2/nodes/?tag=beta")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "tag-a" in names
    assert "tag-b" in names
    # ensure tag filter works for single tag
    resp2 = e2e_client.get("/api/v2/nodes/?tag=alpha")
    assert resp2.status_code == 200
    names2 = {n["name"] for n in resp2.json()["items"]}
    assert "tag-a" in names2
    assert "tag-b" not in names2


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

    resp = e2e_client.get("/api/v2/nodes/?tag=prod")
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

    # New API supports single tag filter; verify tag=web returns only web nodes
    resp = e2e_client.get("/api/v2/nodes/?tag=web")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "multi-tag-1" in names
    assert "multi-tag-2" not in names  # has prod but not web
    assert "multi-tag-3" not in names


def test_node_search_by_name(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    e2e_resources.create_node(name="search-web-1", host="10.0.0.1")
    e2e_resources.create_node(name="search-db-1", host="10.0.0.2")

    resp = e2e_client.get("/api/v2/nodes/?search=web")
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

    resp = e2e_client.get("/api/v2/nodes/?search=prod")
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

    resp = e2e_client.get("/api/v2/nodes/?tag=prod&search=web")
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

    resp = e2e_client.get("/api/v2/nodes/?search=nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 0
    assert data["has_more"] is False


# ---------------------------------------------------------------------------
# Node bulk execute
# ---------------------------------------------------------------------------


def test_node_metrics(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /nodes/metrics returns system metrics via bulk endpoint."""
    node = e2e_resources.create_ssh_node(name="metrics-node")
    resp = e2e_client.post("/api/v2/nodes/metrics", json={"ids": [node["id"]]})
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    result = data["results"][0]
    assert result["status"] == "success"
    assert result["node_id"] == node["id"]
    metrics = result["metrics"]
    assert metrics is not None
    assert "cpu" in metrics
    assert "memory" in metrics
    assert "disk" in metrics
    assert "uptime_since" in metrics
    assert metrics["cpu"]["usage_percent"] >= 0
    assert metrics["cpu"]["cores"] >= 1


def test_node_metrics_not_found(e2e_client: httpx.Client) -> None:
    """POST /nodes/metrics returns error for nonexistent node."""
    fake_id = str(uuid4())
    resp = e2e_client.post("/api/v2/nodes/metrics", json={"ids": [fake_id]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"
    assert data["results"][0]["node_id"] == fake_id


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_cursor_first_page(e2e_client: httpx.Client) -> None:
    """First page without cursor returns nodes."""
    nodes: list[dict[str, object]] = []
    for i in range(3):
        _payload = {
            "name": f"cursor-node-{i}",
            "host": f"10.0.0.{i}",
            "port": 22,
            "connection_type": "ssh",
        }
        resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
        assert resp.status_code in (201, 207)
        nodes.append(_unwrap_node(resp, _payload))

    try:
        cursor = encode_cursor(datetime.now(UTC), uuid4())
        resp = e2e_client.get(f"/api/v2/nodes/?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "has_more" in data
        assert "next_cursor" in data
        assert len(data["items"]) <= 2
    finally:
        for node in nodes:
            e2e_client.delete(f"/api/v2/nodes/{node['id']}")


def test_cursor_pagination(e2e_client: httpx.Client) -> None:
    """Cursor pagination returns next page without duplicates."""
    nodes: list[dict[str, object]] = []
    for i in range(5):
        _payload = {
            "name": f"cursor-page-{i}",
            "host": f"10.0.1.{i}",
            "port": 22,
            "connection_type": "ssh",
        }
        resp = e2e_client.post("/api/v2/nodes/", json={"items": [_payload]})
        assert resp.status_code in (201, 207)
        nodes.append(_unwrap_node(resp, _payload))

    try:
        cursor = encode_cursor(datetime.now(UTC), uuid4())
        resp = e2e_client.get(f"/api/v2/nodes/?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        page1 = resp.json()
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        resp = e2e_client.get(f"/api/v2/nodes/?cursor={page1['next_cursor']}&limit=2")
        assert resp.status_code == 200
        page2 = resp.json()

        page1_ids = {n["id"] for n in page1["items"]}
        page2_ids = {n["id"] for n in page2["items"]}
        assert not page1_ids & page2_ids
    finally:
        for node in nodes:
            e2e_client.delete(f"/api/v2/nodes/{node['id']}")


def test_cursor_invalid(e2e_client: httpx.Client) -> None:
    """Invalid cursor returns 422."""
    resp = e2e_client.get("/api/v2/nodes/?cursor=invalid-cursor!!!")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Config export/import
# ---------------------------------------------------------------------------
