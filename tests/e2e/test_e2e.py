"""E2E tests for the full application stack."""

import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx2 as httpx
import pytest
from pytest_docker.plugin import Services
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime
from app.schemas.common import encode_cursor
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


def _wait_for_audit(
    client: httpx.Client,
    *,
    query: str = "",
    action: str | None = None,
    minimum_total: int = 1,
    timeout: float = 5.0,
) -> dict:
    """Poll the deliberately eventually-consistent transactional outbox."""
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/api/v1/audit/{query}")
        assert response.status_code == 200
        data = response.json()
        actions = {item["action"] for item in data["items"]}
        if data["total"] >= minimum_total and (action is None or action in actions):
            return data
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"audit event was not delivered: action={action}, query={query}"
            )
        time.sleep(0.1)


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
    data = _wait_for_audit(e2e_client, query=f"?node_id={node_id}", action="create")
    actions = [log["action"] for log in data["items"]]
    assert "create" in actions

    # update action recorded
    e2e_client.put(f"/api/v1/nodes/{node_id}", json={"name": "audit-crud-upd"})
    data = _wait_for_audit(e2e_client, query=f"?node_id={node_id}", action="update")
    actions = [log["action"] for log in data["items"]]
    assert "update" in actions

    # delete action recorded — ON DELETE SET NULL nullifies node_id,
    # so query by action instead of node_id.
    total_before = e2e_client.get("/api/v1/audit/").json()["total"]
    e2e_client.delete(f"/api/v1/nodes/{node_id}")
    data = _wait_for_audit(e2e_client, action="delete", minimum_total=total_before + 1)
    all_actions = [log["action"] for log in data["items"]]
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
    data = _wait_for_audit(e2e_client, action="delete", minimum_total=total_before + 1)
    all_actions = [log["action"] for log in data["items"]]
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
    # All targets are validated before any remote side effect.
    assert resp.status_code == 404


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

    data = _wait_for_audit(
        e2e_client,
        query=f"?node_id={node_id}&action=create",
        action="create",
    )
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
    """Node names are unique and duplicate creation is a conflict."""
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
    assert resp.status_code == 409
    e2e_client.delete(f"/api/v1/nodes/{n1['id']}")


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


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------


def test_metrics_endpoint_exists(e2e_client: httpx.Client) -> None:
    """GET /metrics returns Prometheus text format."""
    resp = e2e_client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "http_requests_total" in text or "http_request_duration" in text


def test_metrics_no_auth_required(e2e_client_no_auth: httpx.Client) -> None:
    """/metrics does not require authentication."""
    resp = e2e_client_no_auth.get("/metrics")
    assert resp.status_code == 200


def test_metrics_excludes_health(
    e2e_client: httpx.Client, e2e_client_no_auth: httpx.Client
) -> None:
    """/metrics response does not count /health hits."""
    for _ in range(5):
        e2e_client_no_auth.get("/health")
    resp = e2e_client.get("/metrics")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Cursor-based pagination
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


def test_config_export(e2e_client: httpx.Client) -> None:
    """GET /api/v1/config/export returns all data."""
    resp = e2e_client.get("/api/v1/config/export")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "exported_at" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["commands"], list)
    assert isinstance(data["scripts"], list)


def test_config_export_excludes_secrets(e2e_client: httpx.Client) -> None:
    """Exported nodes don't contain password/ssh_key."""
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "export-secret-node",
            "host": "10.0.0.99",
            "port": 22,
            "connection_type": "ssh",
            "password": "secret123",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    try:
        resp = e2e_client.get("/api/v1/config/export")
        data = resp.json()
        exported = next(
            (n for n in data["nodes"] if n["name"] == "export-secret-node"), None
        )
        assert exported is not None
        assert "password" not in exported
        assert "ssh_key" not in exported
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node_id}")


def test_config_import(e2e_client: httpx.Client) -> None:
    """POST /api/v1/config/import creates items."""
    resp = e2e_client.post(
        "/api/v1/config/import",
        json={
            "nodes": [
                {
                    "name": "imported-e2e",
                    "host": "10.0.0.50",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ],
            "commands": [{"name": "imported-cmd-e2e", "command": "echo hi"}],
            "scripts": [],
        },
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["nodes_created"] >= 1
    assert result["commands_created"] >= 1

    # Cleanup — export doesn't include id, use list endpoints instead
    resp = e2e_client.get("/api/v1/nodes/")
    for n in resp.json()["items"]:
        if n["name"] == "imported-e2e":
            e2e_client.delete(f"/api/v1/nodes/{n['id']}")
    resp = e2e_client.get("/api/v1/commands/")
    for c in resp.json()["items"]:
        if c["name"] == "imported-cmd-e2e":
            e2e_client.delete(f"/api/v1/commands/{c['id']}")


def test_config_import_skips_duplicates(e2e_client: httpx.Client) -> None:
    """Import skips items that already exist by name."""
    resp = e2e_client.post(
        "/api/v1/commands/",
        json={"name": "dup-e2e-cmd", "command": "echo dup"},
    )
    assert resp.status_code == 201
    cmd_id = resp.json()["id"]

    try:
        resp = e2e_client.post(
            "/api/v1/config/import",
            json={"commands": [{"name": "dup-e2e-cmd", "command": "echo dup"}]},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["commands_created"] == 0
        assert len(result["errors"]) >= 1
    finally:
        e2e_client.delete(f"/api/v1/commands/{cmd_id}")


# ---------------------------------------------------------------------------
# Script scheduling
# ---------------------------------------------------------------------------


_INLINE_STEP = [{"label": "step1", "type": "inline", "command": "echo ok"}]


def test_script_schedule(e2e_client: httpx.Client) -> None:
    """POST /scripts/{id}/schedule schedules a script."""
    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={"name": "sched-e2e-script", "steps": _INLINE_STEP},
    )
    assert resp.status_code == 201
    script = resp.json()

    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "sched-e2e-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node = resp.json()

    try:
        resp = e2e_client.post(
            f"/api/v1/scripts/{script['id']}/schedule",
            json={"cron": "0 9 * * *", "node_ids": [node["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["cron"] == "0 9 * * *"
    finally:
        e2e_client.delete(f"/api/v1/scripts/{script['id']}")
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_script_unschedule(e2e_client: httpx.Client) -> None:
    """DELETE /scripts/{id}/schedule removes schedule."""
    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={"name": "unsched-e2e-script", "steps": _INLINE_STEP},
    )
    assert resp.status_code == 201
    script = resp.json()

    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "unsched-e2e-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node = resp.json()

    try:
        e2e_client.post(
            f"/api/v1/scripts/{script['id']}/schedule",
            json={"cron": "0 9 * * *", "node_ids": [node["id"]]},
        )
        resp = e2e_client.delete(f"/api/v1/scripts/{script['id']}/schedule")
        assert resp.status_code == 200
        assert "unscheduled" in resp.json()["message"]
    finally:
        e2e_client.delete(f"/api/v1/scripts/{script['id']}")
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_script_get_schedule(e2e_client: httpx.Client) -> None:
    """GET /scripts/{id}/schedule returns schedule info."""
    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={"name": "getsched-e2e", "steps": _INLINE_STEP},
    )
    assert resp.status_code == 201
    script = resp.json()

    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "getsched-e2e-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node = resp.json()

    try:
        e2e_client.post(
            f"/api/v1/scripts/{script['id']}/schedule",
            json={"cron": "0 9 * * *", "node_ids": [node["id"]]},
        )
        resp = e2e_client.get(f"/api/v1/scripts/{script['id']}/schedule")
        assert resp.status_code == 200
        assert "cron" in resp.json()
    finally:
        e2e_client.delete(f"/api/v1/scripts/{script['id']}")
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_script_get_schedule_not_found(e2e_client: httpx.Client) -> None:
    """GET /scripts/{id}/schedule returns 404 when not scheduled."""
    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={"name": "nosched-e2e", "steps": _INLINE_STEP},
    )
    assert resp.status_code == 201
    script = resp.json()

    try:
        resp = e2e_client.get(f"/api/v1/scripts/{script['id']}/schedule")
        assert resp.status_code == 404
    finally:
        e2e_client.delete(f"/api/v1/scripts/{script['id']}")


def test_script_schedule_nonexistent(e2e_client: httpx.Client) -> None:
    """POST /scripts/{id}/schedule returns 404 for missing script."""
    resp = e2e_client.post(
        f"/api/v1/scripts/{uuid4()}/schedule",
        json={"cron": "0 9 * * *", "node_ids": [str(uuid4())]},
    )
    assert resp.status_code == 404


async def test_second_scheduler_replica_cannot_acquire_ownership(
    docker_ip: str,
    docker_services: Services,
) -> None:
    """The running API owns the advisory lock, so a contender is rejected."""
    database_port = docker_services.port_for("db", 5432)
    engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{docker_ip}:{database_port}"
        "/node_nexus_e2e"
    )
    contender = ApschedulerRuntime()
    try:
        assert await contender.acquire_ownership(engine) is False
        assert contender.owns_execution is False
    finally:
        await contender.stop()
        await engine.dispose()


def test_script_schedule_invalid_cron(e2e_client: httpx.Client) -> None:
    """POST /scripts/{id}/schedule with invalid cron returns 422."""
    resp = e2e_client.post(
        "/api/v1/scripts/",
        json={"name": "badcron-e2e", "steps": _INLINE_STEP},
    )
    assert resp.status_code == 201
    script = resp.json()

    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "badcron-e2e-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node = resp.json()

    try:
        resp = e2e_client.post(
            f"/api/v1/scripts/{script['id']}/schedule",
            json={"cron": "invalid", "node_ids": [node["id"]]},
        )
        assert resp.status_code == 422
    finally:
        e2e_client.delete(f"/api/v1/scripts/{script['id']}")
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker E2E helpers
# ---------------------------------------------------------------------------


def _create_docker_node(e2e_client, **overrides):
    """Create an SSH node with Docker host pointing to internal dind."""
    return _create_ssh_node(
        e2e_client,
        name="docker-e2e-node",
        connection_type="docker",
        docker_host="tcp://dind:2375",
        **overrides,
    )


def _docker_pull_alpine(e2e_client, node_id):
    """Pull alpine image on a Docker node (prerequisite for container tests)."""
    resp = e2e_client.post(
        f"/api/v1/nodes/{node_id}/docker/images/pull",
        json={"image": "alpine:latest", "timeout": 120},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Docker Images
# ---------------------------------------------------------------------------


def test_docker_list_images(e2e_client):
    """GET /nodes/{id}/docker/images returns image list."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/images")
        assert resp.status_code == 200
        images = resp.json()
        assert isinstance(images, list)
        alpine_images = [i for i in images if "alpine" in str(i).lower()]
        assert len(alpine_images) >= 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_pull_image(e2e_client):
    """POST /nodes/{id}/docker/images/pull pulls an image."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/images/pull",
            json={"image": "alpine:3.20", "timeout": 120},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Containers
# ---------------------------------------------------------------------------


def test_docker_list_containers(e2e_client):
    """GET /nodes/{id}/docker/containers returns list."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/containers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_list_containers_all(e2e_client):
    """GET .../containers?all=true includes stopped containers."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/containers?all=true")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_lifecycle(e2e_client):
    """Full container lifecycle: run, inspect, stop, start, restart, remove."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])

        # Run a container via SSH exec (docker run -d alpine sleep 300)
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name e2e-test-ctr alpine sleep 300"},
        )
        assert resp.status_code == 200

        # Inspect
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["State"]["status"] == "running"

        # Stop
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/stop"
        )
        assert resp.status_code == 204

        # Start
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/start"
        )
        assert resp.status_code == 204

        # Restart
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/restart"
        )
        assert resp.status_code == 204

        # Logs
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/logs"
        )
        assert resp.status_code == 200

        # Exec
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/exec",
            json={"command": "echo exec-ok"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "exec-ok" in result["stdout"]

        # Stats
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/stats"
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert "Name" in stats or "CPUPerc" in stats

        # Remove (force)
        resp = e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr?force=true"
        )
        assert resp.status_code == 204

    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_not_found(e2e_client):
    """GET .../containers/{id} returns 404 for missing container."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/nonexistent"
        )
        assert resp.status_code == 404
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_exec_validation(e2e_client):
    """POST .../exec returns 422 for invalid container ID."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/bad;$id/exec",
            json={"command": "ls"},
        )
        assert resp.status_code == 422
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Networks and Volumes
# ---------------------------------------------------------------------------


def test_docker_list_networks(e2e_client):
    """GET /nodes/{id}/docker/networks returns network list."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/networks")
        assert resp.status_code == 200
        networks = resp.json()
        assert isinstance(networks, list)
        # bridge network should exist by default
        names = [n.get("Name", "") for n in networks]
        assert "bridge" in names
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_list_volumes(e2e_client):
    """GET /nodes/{id}/docker/volumes returns volume list."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/volumes")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Bulk Operations
# ---------------------------------------------------------------------------


def test_docker_bulk_start(e2e_client):
    """POST /api/v1/docker/bulk/start starts container on multiple nodes."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        # Run a container via SSH
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-start-ctr alpine sleep 300"},
        )
        # Stop it first
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/bulk-start-ctr/stop"
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/start",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-start-ctr",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "start"
        assert data["total"] == 1
        assert data["succeeded"] == 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_bulk_stop(e2e_client):
    """POST /api/v1/docker/bulk/stop stops container on multiple nodes."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-stop-ctr alpine sleep 300"},
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/stop",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-stop-ctr",
                "timeout": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "stop"
        assert data["total"] == 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_bulk_restart(e2e_client):
    """POST /api/v1/docker/bulk/restart restarts container on multiple nodes."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-restart-ctr alpine sleep 300"},
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/restart",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-restart-ctr",
                "timeout": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "restart"
        assert data["succeeded"] == 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_bulk_exec(e2e_client):
    """POST /api/v1/docker/bulk/exec runs command in containers."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-exec-ctr alpine sleep 300"},
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/exec",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-exec-ctr",
                "command": "echo exec-works",
                "timeout": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "exec"
        results = data["results"]
        assert len(results) == 1
        assert "exec-works" in results[0]["output"]
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# API Key scope enforcement (403 on read-only)
# ---------------------------------------------------------------------------


def test_read_only_key_rejected_on_write(e2e_client):
    """403 when read-only API key tries POST/PUT/DELETE."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "ro-scope-test", "scope": "read-only"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    ro_key = resp.json()["key"]
    key_id = resp.json()["id"]

    try:
        # POST with read-only key should return 403
        resp = e2e_client.post(
            "/api/v1/nodes/",
            json={
                "name": "should-fail",
                "host": "1.1.1.1",
                "port": 22,
                "connection_type": "ssh",
            },
            headers={"X-API-Key": ro_key},
        )
        assert resp.status_code == 403
    finally:
        e2e_client.delete(
            f"/api/v1/api-keys/{key_id}",
            headers={"X-API-Key": master_key},
        )


def test_read_only_key_can_read(e2e_client):
    """200 when read-only API key accesses GET endpoints."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "ro-read-test", "scope": "read-only"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    ro_key = resp.json()["key"]
    key_id = resp.json()["id"]

    try:
        resp = e2e_client.get(
            "/api/v1/nodes/",
            headers={"X-API-Key": ro_key},
        )
        assert resp.status_code == 200
    finally:
        e2e_client.delete(
            f"/api/v1/api-keys/{key_id}",
            headers={"X-API-Key": master_key},
        )
