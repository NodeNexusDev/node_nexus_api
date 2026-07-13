"""E2E tests for the full application stack."""

import httpx

from tests.e2e.conftest import ServicePorts

_NODE_PAYLOAD = {
    "name": "e2e-node",
    "host": "10.0.0.1",
    "port": 22,
    "connection_type": "ssh",
}


def _create_node(e2e_client: httpx.Client, **overrides) -> dict:
    """Helper to create a basic node for tests."""
    data = {**_NODE_PAYLOAD, **overrides}
    resp = e2e_client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


def _create_ssh_node(e2e_client: httpx.Client, **overrides) -> dict:
    """Helper to create an SSH node for tests."""
    data = {
        "name": "ssh-node",
        "host": "ssh-server",
        "port": 2222,
        "connection_type": "ssh",
        "username": "testuser",
        "password": "testpass",
    }
    data.update(overrides)
    resp = e2e_client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


def test_health(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


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
    resp = e2e_client.put(
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


def test_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={"name": "incomplete"},
    )
    assert resp.status_code == 422


def test_not_found_errors(e2e_client: httpx.Client) -> None:
    import uuid

    fake_id = str(uuid.uuid4())

    resp = e2e_client.get(f"/api/v1/nodes/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.put(
        f"/api/v1/nodes/{fake_id}",
        json={"name": "x"},
    )
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v1/nodes/{fake_id}")
    assert resp.status_code == 404


def test_ssh_check_connectivity(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="ssh-test")
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_ssh_execute_command(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="ssh-exec")
    resp = e2e_client.post(
        f"/api/v1/nodes/{node['id']}/execute",
        json={"command": "echo e2e-works"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["stdout"].strip() == "e2e-works"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


def test_ssh_execute_command_non_zero_exit(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="ssh-fail")
    resp = e2e_client.post(
        f"/api/v1/nodes/{node['id']}/execute",
        json={"command": "exit 42"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["exit_code"] == 42


def test_ssh_execute_command_stderr(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="ssh-stderr")
    resp = e2e_client.post(
        f"/api/v1/nodes/{node['id']}/execute",
        json={"command": "echo error-output >&2"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert "error-output" in result["stderr"]
    assert result["exit_code"] == 0


def test_ssh_check_not_found(e2e_client: httpx.Client) -> None:
    import uuid

    resp = e2e_client.post(f"/api/v1/nodes/{uuid.uuid4()}/check")
    assert resp.status_code == 404


def test_ssh_execute_not_found(e2e_client: httpx.Client) -> None:
    import uuid

    resp = e2e_client.post(
        f"/api/v1/nodes/{uuid.uuid4()}/execute",
        json={"command": "ls"},
    )
    assert resp.status_code == 404


def test_pagination_page2(e2e_client: httpx.Client) -> None:
    for i in range(3):
        e2e_client.post(
            "/api/v1/nodes/",
            json={
                "name": f"page-test-{i}",
                "host": "10.0.0.1",
                "port": 22,
                "connection_type": "ssh",
            },
        )

    resp = e2e_client.get("/api/v1/nodes/?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["size"] == 2


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------


def test_audit_log_endpoint(e2e_client: httpx.Client) -> None:
    _create_node(e2e_client, name="audit-probe")

    resp = e2e_client.get("/api/v1/audit/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data
    assert "page" in data and "size" in data
    assert data["total"] >= 1

    log = data["items"][0]
    assert "id" in log
    assert "action" in log
    assert "created_at" in log
    assert "node_id" in log


def test_audit_logs_track_crud_operations(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="audit-crud")
    node_id = node["id"]

    # create action recorded
    resp = e2e_client.get(f"/api/v1/audit/?node_id={node_id}")
    actions = [log["action"] for log in resp.json()["items"]]
    assert "create" in actions

    # update action recorded
    e2e_client.put(f"/api/v1/nodes/{node_id}", json={"name": "audit-crud-upd"})
    resp = e2e_client.get(f"/api/v1/audit/?node_id={node_id}")
    actions = [log["action"] for log in resp.json()["items"]]
    assert "update" in actions

    # delete action recorded — ON DELETE SET NULL nullifies node_id,
    # so query by action instead of node_id.
    total_before = e2e_client.get("/api/v1/audit/").json()["total"]
    e2e_client.delete(f"/api/v1/nodes/{node_id}")
    resp = e2e_client.get("/api/v1/audit/")
    assert resp.json()["total"] >= total_before
    all_actions = [log["action"] for log in resp.json()["items"]]
    assert "delete" in all_actions


def test_delete_creates_audit_log_and_removes_node(
    e2e_client: httpx.Client,
) -> None:
    """Regression: FK violation used to roll back DELETE silently."""
    node = _create_node(e2e_client, name="audit-fk-regression")
    node_id = node["id"]

    total_before = e2e_client.get("/api/v1/audit/").json()["total"]
    resp = e2e_client.delete(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 204

    # node is gone
    resp = e2e_client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 404

    # audit entry exists (ON DELETE SET NULL nullifies node_id,
    # so verify total grew and a "delete" action appeared)
    resp = e2e_client.get("/api/v1/audit/")
    assert resp.json()["total"] >= total_before
    all_actions = [log["action"] for log in resp.json()["items"]]
    assert "delete" in all_actions


def test_audit_log_filter_by_action(e2e_client: httpx.Client) -> None:
    _create_node(e2e_client, name="audit-filter")

    resp = e2e_client.get("/api/v1/audit/?action=create")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    for log in resp.json()["items"]:
        assert log["action"] == "create"


# ---------------------------------------------------------------------------
# SSH wrong credentials
# ---------------------------------------------------------------------------


def test_ssh_check_wrong_credentials(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(
        e2e_client, name="ssh-bad", username="testuser", password="wrongpass"
    )
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreachable"


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def test_security_headers(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-xss-protection"] == "1; mode=block"
    assert "max-age=31536000" in resp.headers["strict-transport-security"]


# ---------------------------------------------------------------------------
# Partial update
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

    resp = e2e_client.put(
        f"/api/v1/nodes/{node_id}", json={"name": "partial-new"}
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "partial-new"
    assert updated["host"] == original_host
    assert updated["port"] == 2222


# ---------------------------------------------------------------------------
# CORS preflight
# ---------------------------------------------------------------------------


def test_cors_preflight(e2e_client: httpx.Client) -> None:
    resp = e2e_client.options(
        "/api/v1/nodes/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods
