"""E2E tests for the full application stack."""

from uuid import uuid4

import httpx2 as httpx
import pytest

from tests.e2e.conftest import ServicePorts

pytestmark = pytest.mark.docker

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
    """Helper to create an SSH node for tests.

    Uses Docker compose service name "ssh-server" as host — the API
    resolves it via Docker's internal DNS.  For tests that need to
    connect via mapped ports, pass host/port via **overrides.
    """
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
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_readiness(e2e_client: httpx.Client) -> None:
    """Readiness probe checks database connectivity."""
    resp = e2e_client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"


def test_readiness_no_auth(e2e_client_no_auth: httpx.Client) -> None:
    """Readiness probe does not require authentication."""
    resp = e2e_client_no_auth.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"


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
    fake_id = str(uuid4())

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
    resp = e2e_client.post(f"/api/v1/nodes/{uuid4()}/check")
    assert resp.status_code == 404


def test_ssh_execute_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        f"/api/v1/nodes/{uuid4()}/execute",
        json={"command": "ls"},
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
    node = _create_node(e2e_client, name="audit-filter")

    resp = e2e_client.get("/api/v1/audit/?action=create")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    for log in resp.json()["items"]:
        assert log["action"] == "create"

    e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# SSH wrong credentials
# ---------------------------------------------------------------------------


def test_ssh_check_wrong_credentials(e2e_client: httpx.Client) -> None:
    """Wrong credentials return 200 with status="unreachable".

    The /check endpoint always returns 200 — it reports connectivity
    status via the response body, not HTTP status codes.
    """
    node = _create_ssh_node(
        e2e_client, name="ssh-bad", username="testuser", password="wrongpass"
    )
    resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreachable"

    e2e_client.delete(f"/api/v1/nodes/{node['id']}")


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

    resp = e2e_client.put(f"/api/v1/nodes/{node_id}", json={"name": "partial-new"})
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

    # Also verify that a regular GET response includes CORS headers
    resp = e2e_client.get(
        "/api/v1/nodes/",
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# Command template CRUD
# ---------------------------------------------------------------------------


def _create_command(e2e_client: httpx.Client, **overrides) -> dict:
    """Helper to create a command template."""
    data = {
        "name": "e2e-command",
        "command": "echo test",
        "description": "E2E test command",
        **overrides,
    }
    resp = e2e_client.post("/api/v1/commands/", json=data)
    assert resp.status_code == 201
    return resp.json()


def test_command_crud_full_cycle(e2e_client: httpx.Client) -> None:
    # Create
    cmd = _create_command(e2e_client, name="cmd-create")
    cmd_id = cmd["id"]
    assert cmd["name"] == "cmd-create"
    assert cmd["command"] == "echo test"

    # Read
    resp = e2e_client.get(f"/api/v1/commands/{cmd_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "cmd-create"

    # Read all
    resp = e2e_client.get("/api/v1/commands/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data
    assert data["total"] >= 1

    # Update
    resp = e2e_client.put(
        f"/api/v1/commands/{cmd_id}",
        json={"name": "cmd-updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "cmd-updated"

    # Delete
    resp = e2e_client.delete(f"/api/v1/commands/{cmd_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = e2e_client.get(f"/api/v1/commands/{cmd_id}")
    assert resp.status_code == 404


def test_command_create_with_parameters(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/commands/",
        json={
            "name": "param-cmd",
            "command": "systemctl restart {service}",
            "parameters": [{"name": "service", "type": "string", "required": True}],
        },
    )
    assert resp.status_code == 201
    cmd = resp.json()
    assert cmd["parameters"] is not None
    assert len(cmd["parameters"]) == 1
    assert cmd["parameters"][0]["name"] == "service"


def test_command_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post("/api/v1/commands/", json={"name": "no-cmd"})
    assert resp.status_code == 422


def test_command_not_found(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())
    resp = e2e_client.get(f"/api/v1/commands/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.put(f"/api/v1/commands/{fake_id}", json={"name": "x"})
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v1/commands/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Script CRUD
# ---------------------------------------------------------------------------


def _create_script(e2e_client: httpx.Client, **overrides) -> dict:
    """Helper to create a script."""
    steps = [
        {
            "label": "Check disk",
            "type": "inline",
            "command": "df -h",
            "on_failure": "stop",
        }
    ]
    data = {
        "name": "e2e-script",
        "description": "E2E test script",
        "steps": steps,
        **overrides,
    }
    resp = e2e_client.post("/api/v1/scripts/", json=data)
    assert resp.status_code == 201
    return resp.json()


def test_script_crud_full_cycle(e2e_client: httpx.Client) -> None:
    # Create
    script = _create_script(e2e_client, name="script-create")
    script_id = script["id"]
    assert script["name"] == "script-create"
    assert len(script["steps"]) == 1

    # Read
    resp = e2e_client.get(f"/api/v1/scripts/{script_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "script-create"

    # Read all
    resp = e2e_client.get("/api/v1/scripts/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data
    assert data["total"] >= 1

    # Update
    resp = e2e_client.put(
        f"/api/v1/scripts/{script_id}",
        json={"name": "script-updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "script-updated"

    # Delete
    resp = e2e_client.delete(f"/api/v1/scripts/{script_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = e2e_client.get(f"/api/v1/scripts/{script_id}")
    assert resp.status_code == 404


def test_script_create_multiple_steps(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={
            "name": "multi-step",
            "steps": [
                {"label": "Step 1", "type": "inline", "command": "echo 1"},
                {
                    "label": "Step 2",
                    "type": "inline",
                    "command": "echo 2",
                    "on_failure": "continue",
                },
            ],
        },
    )
    assert resp.status_code == 201
    script = resp.json()
    assert len(script["steps"]) == 2
    assert script["steps"][0]["label"] == "Step 1"
    assert script["steps"][1]["on_failure"] == "continue"


def test_script_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post("/api/v1/scripts/", json={"name": "no-steps"})
    assert resp.status_code == 422


def test_script_not_found(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())
    resp = e2e_client.get(f"/api/v1/scripts/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.put(f"/api/v1/scripts/{fake_id}", json={"name": "x"})
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v1/scripts/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Script execution (requires SSH node)
# ---------------------------------------------------------------------------


def test_script_execute_on_ssh_node(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="script-exec")
    script = _create_script(e2e_client, name="exec-script")

    resp = e2e_client.post(
        f"/api/v1/scripts/{script['id']}/execute",
        json={"node_ids": [node["id"]], "params": {}},
    )
    assert resp.status_code == 200
    batch = resp.json()
    assert batch["script_id"] == script["id"]
    assert len(batch["results"]) == 1
    result = batch["results"][0]
    assert result["node_id"] == node["id"]
    assert result["status"] == "completed"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["exit_code"] == 0


def test_script_execute_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        f"/api/v1/scripts/{uuid4()}/execute",
        json={"node_ids": [str(uuid4())], "params": {}},
    )
    assert resp.status_code == 404


def test_script_execute_node_not_found(e2e_client: httpx.Client) -> None:
    script = _create_script(e2e_client, name="no-node-script")
    resp = e2e_client.post(
        f"/api/v1/scripts/{script['id']}/execute",
        json={"node_ids": [str(uuid4())], "params": {}},
    )
    # Script execution returns 200 with per-node failure status
    assert resp.status_code == 200
    batch = resp.json()
    assert len(batch["results"]) == 1
    assert batch["results"][0]["status"] == "failed"


def test_script_executions_history(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="script-hist")
    script = _create_script(e2e_client, name="hist-script")

    # Execute
    e2e_client.post(
        f"/api/v1/scripts/{script['id']}/execute",
        json={"node_ids": [node["id"]], "params": {}},
    )

    # Check history
    resp = e2e_client.get(f"/api/v1/scripts/{script['id']}/executions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    execution = data["items"][0]
    assert execution["status"] == "completed"
    assert execution["node_id"] == node["id"]


def test_script_executions_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get(f"/api/v1/scripts/{uuid4()}/executions")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Connection type validation
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


def test_command_execute_on_node(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="cmd-exec-node")
    cmd = _create_command(e2e_client, name="cmd-exec", command="echo hello-cmd")

    resp = e2e_client.post(
        f"/api/v1/commands/{cmd['id']}/execute",
        json={"node_id": node["id"], "params": {}},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["stdout"].strip() == "hello-cmd"
    assert result["exit_code"] == 0


def test_command_execute_not_found(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="cmd-nf-node")
    resp = e2e_client.post(
        f"/api/v1/commands/{uuid4()}/execute",
        json={"node_id": node["id"], "params": {}},
    )
    assert resp.status_code == 404


def test_command_execute_node_not_found(e2e_client: httpx.Client) -> None:
    cmd = _create_command(e2e_client, name="cmd-no-node")
    resp = e2e_client.post(
        f"/api/v1/commands/{cmd['id']}/execute",
        json={"node_id": str(uuid4()), "params": {}},
    )
    assert resp.status_code == 404


def test_command_execute_missing_required_param(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="cmd-param-node")
    cmd = _create_command(
        e2e_client,
        name="cmd-param",
        command="echo {greeting}",
        parameters=[{"name": "greeting", "type": "string", "required": True}],
    )

    resp = e2e_client.post(
        f"/api/v1/commands/{cmd['id']}/execute",
        json={"node_id": node["id"], "params": {}},
    )
    assert resp.status_code == 422


def test_command_execute_with_params(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="cmd-params-node")
    cmd = _create_command(
        e2e_client,
        name="cmd-with-params",
        command="echo {greeting}",
        parameters=[{"name": "greeting", "type": "string", "required": True}],
    )

    resp = e2e_client.post(
        f"/api/v1/commands/{cmd['id']}/execute",
        json={"node_id": node["id"], "params": {"greeting": "world"}},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["stdout"].strip() == "world"
    assert result["exit_code"] == 0


# ---------------------------------------------------------------------------
# API key CRUD
# ---------------------------------------------------------------------------


def _get_master_key() -> str:
    """Return the master API key used in the e2e Docker environment."""
    return "e2e-master-key-12345"


def test_api_key_create(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "e2e-key-create"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "e2e-key-create"
    assert data["key"].startswith("nnk_")
    assert data["key_prefix"] == data["key"][:8]


def test_api_key_list(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    # Create a key first
    e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "e2e-key-list"},
        headers={"X-API-Key": master_key},
    )

    resp = e2e_client.get(
        "/api/v1/api-keys/",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


def test_api_key_revoke(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "e2e-key-revoke"},
        headers={"X-API-Key": master_key},
    )
    key_id = resp.json()["id"]
    generated_key = resp.json()["key"]

    # Revoke
    resp = e2e_client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 204

    # Verify revoked key is rejected
    resp = e2e_client.get(
        "/api/v1/nodes/",
        headers={"X-API-Key": generated_key},
    )
    assert resp.status_code == 401

    # Verify list shows key as inactive
    resp = e2e_client.get(
        "/api/v1/api-keys/",
        headers={"X-API-Key": master_key},
    )
    items = resp.json()["items"]
    revoked = [k for k in items if k["id"] == key_id]
    assert len(revoked) == 1
    assert revoked[0]["is_active"] is False


def test_api_key_revoke_not_found(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    resp = e2e_client.delete(
        f"/api/v1/api-keys/{uuid4()}",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 404


def test_api_key_use_generated_key(e2e_client: httpx.Client) -> None:
    """Created API key can authenticate subsequent requests."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "e2e-key-auth"},
        headers={"X-API-Key": master_key},
    )
    generated_key = resp.json()["key"]

    # Use generated key to access a protected endpoint
    resp = e2e_client.get(
        "/api/v1/nodes/",
        headers={"X-API-Key": generated_key},
    )
    assert resp.status_code == 200


def test_api_key_missing_header(e2e_client_no_auth: httpx.Client) -> None:
    resp = e2e_client_no_auth.get("/api/v1/nodes/")
    assert resp.status_code == 401


def test_api_key_invalid_key(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get(
        "/api/v1/nodes/",
        headers={"X-API-Key": "nnk_invalid_key_12345678901234567890"},
    )
    assert resp.status_code == 401


def test_api_key_create_validation_error(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": ""},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Audit log pagination and combined filters
# ---------------------------------------------------------------------------


def test_audit_log_pagination(e2e_client: httpx.Client) -> None:
    # Create multiple nodes to generate audit entries
    created: list[str] = []
    for i in range(3):
        node = _create_node(e2e_client, name=f"audit-page-{i}")
        created.append(node["id"])

    resp = e2e_client.get("/api/v1/audit/?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["size"] == 2

    for node_id in created:
        e2e_client.delete(f"/api/v1/nodes/{node_id}")


def test_audit_log_combined_filters(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="audit-combined")
    node_id = node["id"]

    resp = e2e_client.get(f"/api/v1/audit/?node_id={node_id}&action=create")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    for log in data["items"]:
        assert log["action"] == "create"
        # node_id may be null for deleted nodes, but for existing ones it matches
        if log["node_id"] is not None:
            assert log["node_id"] == node_id

    e2e_client.delete(f"/api/v1/nodes/{node_id}")


# ---------------------------------------------------------------------------
# Command and script pagination
# ---------------------------------------------------------------------------


def test_command_pagination(e2e_client: httpx.Client) -> None:
    created: list[str] = []
    for i in range(3):
        cmd = _create_command(e2e_client, name=f"page-cmd-{i}")
        created.append(cmd["id"])

    resp = e2e_client.get("/api/v1/commands/?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["size"] == 2

    for cmd_id in created:
        e2e_client.delete(f"/api/v1/commands/{cmd_id}")


def test_script_pagination(e2e_client: httpx.Client) -> None:
    created: list[str] = []
    for i in range(3):
        script = _create_script(e2e_client, name=f"page-script-{i}")
        created.append(script["id"])

    resp = e2e_client.get("/api/v1/scripts/?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["size"] == 2

    for script_id in created:
        e2e_client.delete(f"/api/v1/scripts/{script_id}")


# ---------------------------------------------------------------------------
# Script execute with command reference steps
# ---------------------------------------------------------------------------


def test_script_execute_with_command_reference(e2e_client: httpx.Client) -> None:
    node = _create_ssh_node(e2e_client, name="script-cmd-ref")
    cmd = _create_command(e2e_client, name="ref-cmd", command="echo ref-ok")

    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={
            "name": "cmd-ref-script",
            "steps": [
                {
                    "label": "Run referenced cmd",
                    "type": "command",
                    "command_id": cmd["id"],
                    "on_failure": "stop",
                }
            ],
        },
    )
    assert resp.status_code == 201
    script = resp.json()

    resp = e2e_client.post(
        f"/api/v1/scripts/{script['id']}/execute",
        json={"node_ids": [node["id"]], "params": {}},
    )
    assert resp.status_code == 200
    batch = resp.json()
    assert len(batch["results"]) == 1
    result = batch["results"][0]
    assert result["status"] == "completed"
    assert result["steps"][0]["stdout"].strip() == "ref-ok"


def test_script_execute_multi_node(e2e_client: httpx.Client) -> None:
    node1 = _create_ssh_node(e2e_client, name="multi-node-1")
    node2 = _create_ssh_node(e2e_client, name="multi-node-2")
    script = _create_script(e2e_client, name="multi-script")

    resp = e2e_client.post(
        f"/api/v1/scripts/{script['id']}/execute",
        json={"node_ids": [node1["id"], node2["id"]], "params": {}},
    )
    assert resp.status_code == 200
    batch = resp.json()
    assert len(batch["results"]) == 2
    node_ids = {r["node_id"] for r in batch["results"]}
    assert node1["id"] in node_ids
    assert node2["id"] in node_ids
    for r in batch["results"]:
        assert r["status"] == "completed"


# ---------------------------------------------------------------------------
# Command partial update and edge cases
# ---------------------------------------------------------------------------


def test_command_partial_update(e2e_client: httpx.Client) -> None:
    cmd = _create_command(e2e_client, name="cmd-partial")

    resp = e2e_client.put(
        f"/api/v1/commands/{cmd['id']}",
        json={"name": "cmd-partial-updated"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "cmd-partial-updated"
    assert updated["command"] == "echo test"  # unchanged


def test_script_partial_update(e2e_client: httpx.Client) -> None:
    script = _create_script(e2e_client, name="script-partial")

    resp = e2e_client.put(
        f"/api/v1/scripts/{script['id']}",
        json={"name": "script-partial-updated"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "script-partial-updated"
    assert len(updated["steps"]) == 1  # steps unchanged


# ---------------------------------------------------------------------------
# Node port validation
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


def test_create_node_duplicate_name(e2e_client: httpx.Client) -> None:
    """Nodes with same name should be allowed (no unique constraint on name)."""
    n1 = _create_node(e2e_client, name="dup-name")
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "dup-name",
            "host": "10.0.0.2",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    n2 = resp.json()

    for n in (n1, n2):
        e2e_client.delete(f"/api/v1/nodes/{n['id']}")


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


def test_node_get_all_tags(e2e_client: httpx.Client) -> None:
    n1 = _create_node(e2e_client, name="tag-a", tags=["alpha", "beta"])
    n2 = _create_node(e2e_client, name="tag-b", tags=["beta", "gamma"])

    resp = e2e_client.get("/api/v1/nodes/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert "alpha" in tags
    assert "beta" in tags
    assert "gamma" in tags

    for n in (n1, n2):
        e2e_client.delete(f"/api/v1/nodes/{n['id']}")


def test_node_add_tag(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="add-tag-node", tags=["existing"])

    resp = e2e_client.post(
        f"/api/v1/nodes/{node['id']}/tags",
        json={"tag": "new-tag"},
    )
    assert resp.status_code == 200
    assert "new-tag" in resp.json()["tags"]
    assert "existing" in resp.json()["tags"]

    e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_node_add_tag_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        f"/api/v1/nodes/{uuid4()}/tags",
        json={"tag": "x"},
    )
    assert resp.status_code == 404


def test_node_remove_tag(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="rm-tag-node", tags=["keep", "remove"])

    resp = e2e_client.request(
        "DELETE",
        f"/api/v1/nodes/{node['id']}/tags",
        json={"tag": "remove"},
    )
    assert resp.status_code == 200
    assert "keep" in resp.json()["tags"]
    assert "remove" not in resp.json()["tags"]

    e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_node_remove_tag_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.request(
        "DELETE",
        f"/api/v1/nodes/{uuid4()}/tags",
        json={"tag": "x"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Node filtering and search
# ---------------------------------------------------------------------------


def test_node_filter_by_tags(e2e_client: httpx.Client) -> None:
    n1 = _create_node(e2e_client, name="filter-prod-web", tags=["prod", "web"])
    n2 = _create_node(e2e_client, name="filter-prod-db", tags=["prod", "db"])
    n3 = _create_node(e2e_client, name="filter-staging", tags=["staging"])

    resp = e2e_client.get("/api/v1/nodes/?tags=prod")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "filter-prod-web" in names
    assert "filter-prod-db" in names
    assert "filter-staging" not in names

    for n in (n1, n2, n3):
        e2e_client.delete(f"/api/v1/nodes/{n['id']}")


def test_node_filter_by_multiple_tags(e2e_client: httpx.Client) -> None:
    n1 = _create_node(e2e_client, name="multi-tag-1", tags=["prod", "web"])
    n2 = _create_node(e2e_client, name="multi-tag-2", tags=["prod", "db"])
    n3 = _create_node(e2e_client, name="multi-tag-3", tags=["prod"])

    resp = e2e_client.get("/api/v1/nodes/?tags=prod,web")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "multi-tag-1" in names
    assert "multi-tag-2" not in names  # has prod but not web

    for n in (n1, n2, n3):
        e2e_client.delete(f"/api/v1/nodes/{n['id']}")


def test_node_search_by_name(e2e_client: httpx.Client) -> None:
    n1 = _create_node(e2e_client, name="search-web-1", host="10.0.0.1")
    n2 = _create_node(e2e_client, name="search-db-1", host="10.0.0.2")

    resp = e2e_client.get("/api/v1/nodes/?search=web")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "search-web-1" in names
    assert "search-db-1" not in names

    for n in (n1, n2):
        e2e_client.delete(f"/api/v1/nodes/{n['id']}")


def test_node_search_by_host(e2e_client: httpx.Client) -> None:
    n1 = _create_node(e2e_client, name="host-alpha", host="prod.example.com")
    n2 = _create_node(e2e_client, name="host-beta", host="staging.example.com")

    resp = e2e_client.get("/api/v1/nodes/?search=prod")
    assert resp.status_code == 200
    data = resp.json()
    names = {n["name"] for n in data["items"]}
    assert "host-alpha" in names
    assert "host-beta" not in names

    for n in (n1, n2):
        e2e_client.delete(f"/api/v1/nodes/{n['id']}")


def test_node_filter_by_tags_and_search(e2e_client: httpx.Client) -> None:
    n1 = _create_node(
        e2e_client, name="combo-web-prod", host="10.0.0.1", tags=["prod", "web"]
    )
    n2 = _create_node(
        e2e_client, name="combo-db-prod", host="10.0.0.2", tags=["prod", "db"]
    )
    n3 = _create_node(
        e2e_client,
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

    for n in (n1, n2, n3):
        e2e_client.delete(f"/api/v1/nodes/{n['id']}")


def test_node_filter_empty_result(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="no-match", tags=["dev"])

    resp = e2e_client.get("/api/v1/nodes/?search=nonexistent")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Node bulk execute
# ---------------------------------------------------------------------------


def test_bulk_execute_by_ids(e2e_client: httpx.Client) -> None:
    node1 = _create_ssh_node(e2e_client, name="bulk-1")
    node2 = _create_ssh_node(e2e_client, name="bulk-2")

    resp = e2e_client.post(
        "/api/v1/nodes/bulk/execute",
        json={
            "command": "echo bulk-ok",
            "node_ids": [node1["id"], node2["id"]],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["command"] == "echo bulk-ok"
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0

    node_ids = {r["node_id"] for r in data["results"]}
    assert node1["id"] in node_ids
    assert node2["id"] in node_ids

    for r in data["results"]:
        assert r["stdout"].strip() == "bulk-ok"
        assert r["exit_code"] == 0


def test_bulk_execute_by_tags(e2e_client: httpx.Client) -> None:
    node1 = _create_ssh_node(e2e_client, name="bulk-tag-1", tags=["bulk-test"])
    node2 = _create_ssh_node(e2e_client, name="bulk-tag-2", tags=["bulk-test"])
    _create_ssh_node(e2e_client, name="bulk-tag-other", tags=["other"])

    resp = e2e_client.post(
        "/api/v1/nodes/bulk/execute",
        json={"command": "echo tagged", "tags": ["bulk-test"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    node_ids = {r["node_id"] for r in data["results"]}
    assert node1["id"] in node_ids
    assert node2["id"] in node_ids


def test_bulk_execute_no_nodes(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/bulk/execute",
        json={"command": "ls", "node_ids": [str(uuid4())]},
    )
    assert resp.status_code == 404


def test_bulk_execute_partial_failure(e2e_client: httpx.Client) -> None:
    """One good node + one unreachable node = partial success."""
    good_node = _create_ssh_node(e2e_client, name="bulk-good")
    bad_node = _create_node(
        e2e_client,
        name="bulk-bad",
        host="192.0.2.1",  # TEST-NET — unreachable
        port=22,
    )

    resp = e2e_client.post(
        "/api/v1/nodes/bulk/execute",
        json={
            "command": "echo partial",
            "node_ids": [good_node["id"], bad_node["id"]],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1

    results_by_id = {r["node_id"]: r for r in data["results"]}
    assert results_by_id[good_node["id"]]["exit_code"] == 0
    assert results_by_id[bad_node["id"]]["exit_code"] != 0


def test_bulk_execute_validation_no_targets(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/bulk/execute",
        json={"command": "ls"},
    )
    assert resp.status_code == 422


def test_bulk_execute_validation_empty_command(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/bulk/execute",
        json={"command": "", "node_ids": ["00000000-0000-0000-0000-000000000001"]},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Readiness probe
# ---------------------------------------------------------------------------


def test_readiness_probe(e2e_client: httpx.Client) -> None:
    """GET /ready checks database connectivity."""
    resp = e2e_client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"


# ---------------------------------------------------------------------------
# API Key PATCH and scope
# ---------------------------------------------------------------------------


def test_api_key_patch_name(e2e_client: httpx.Client) -> None:
    """PATCH /api-keys/{id} can update name."""
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "patch-test"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    # Patch
    resp = e2e_client.patch(
        f"/api/v1/api-keys/{key_id}",
        json={"name": "patched-name"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "patched-name"

    # Cleanup
    e2e_client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


def test_api_key_patch_scope(e2e_client: httpx.Client) -> None:
    """PATCH /api-keys/{id} can update scope."""
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "scope-test"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    # Patch scope to read-only
    resp = e2e_client.patch(
        f"/api/v1/api-keys/{key_id}",
        json={"scope": "read-only"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "read-only"

    # Cleanup
    e2e_client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


def test_api_key_patch_expires_at(e2e_client: httpx.Client) -> None:
    """PATCH /api-keys/{id} can set expires_at."""
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "expires-test"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    # Patch expires_at
    resp = e2e_client.patch(
        f"/api/v1/api-keys/{key_id}",
        json={"expires_at": "2099-12-31T23:59:59Z"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    assert resp.json()["expires_at"] is not None

    # Cleanup
    e2e_client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


# ---------------------------------------------------------------------------
# Command and Script tags
# ---------------------------------------------------------------------------


def test_command_with_tags(e2e_client: httpx.Client) -> None:
    """Commands can be created with tags and filtered by tag."""
    # Create command with tags
    resp = e2e_client.post(
        "/api/v1/commands/",
        json={
            "name": "tagged-cmd",
            "command": "echo tagged",
            "tags": ["deploy", "prod"],
        },
    )
    assert resp.status_code == 201
    cmd = resp.json()
    assert sorted(cmd["tags"]) == ["deploy", "prod"]
    cmd_id = cmd["id"]

    # Filter by tag
    resp = e2e_client.get("/api/v1/commands/?tag=deploy")
    assert resp.status_code == 200
    data = resp.json()
    names = {c["name"] for c in data["items"]}
    assert "tagged-cmd" in names

    # Cleanup
    e2e_client.delete(f"/api/v1/commands/{cmd_id}")


def test_script_with_tags(e2e_client: httpx.Client) -> None:
    """Scripts can be created with tags and filtered by tag."""
    # Create script with tags
    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={
            "name": "tagged-script",
            "steps": [{"label": "Step 1", "type": "inline", "command": "echo ok"}],
            "tags": ["deploy", "staging"],
        },
    )
    assert resp.status_code == 201
    script = resp.json()
    assert sorted(script["tags"]) == ["deploy", "staging"]
    script_id = script["id"]

    # Filter by tag
    resp = e2e_client.get("/api/v1/scripts/?tag=deploy")
    assert resp.status_code == 200
    data = resp.json()
    names = {s["name"] for s in data["items"]}
    assert "tagged-script" in names

    # Cleanup
    e2e_client.delete(f"/api/v1/scripts/{script_id}")


# ---------------------------------------------------------------------------
# Audit log cleanup
# ---------------------------------------------------------------------------


def test_audit_delete_requires_master_key(e2e_client: httpx.Client) -> None:
    """DELETE /audit requires master key."""
    # Create a non-master key
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "non-master-key"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    generated_key = resp.json()["key"]
    key_id = resp.json()["id"]

    # Try to delete audit logs with non-master key
    resp = e2e_client.delete(
        "/api/v1/audit/?confirm=yes",
        headers={"X-API-Key": generated_key},
    )
    assert resp.status_code == 403

    # Cleanup
    e2e_client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


def test_audit_delete_requires_confirm(e2e_client: httpx.Client) -> None:
    """DELETE /audit without confirm=yes returns 422."""
    master_key = _get_master_key()
    resp = e2e_client.delete(
        "/api/v1/audit/",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 422


def test_audit_delete_with_master_key(e2e_client: httpx.Client) -> None:
    """DELETE /audit with master key and confirm=yes succeeds."""
    master_key = _get_master_key()
    resp = e2e_client.delete(
        "/api/v1/audit/?confirm=yes",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted_count" in data


# ---------------------------------------------------------------------------
# Node metrics
# ---------------------------------------------------------------------------


def test_node_metrics(e2e_client: httpx.Client) -> None:
    """GET /nodes/{id}/metrics returns system metrics."""
    node = _create_ssh_node(e2e_client, name="metrics-node")
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


def test_rate_limit_headers(e2e_client: httpx.Client) -> None:
    """Responses include rate limit headers."""
    resp = e2e_client.get("/api/v1/nodes/")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers
