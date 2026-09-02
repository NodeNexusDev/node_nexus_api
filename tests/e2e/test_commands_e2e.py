"""E2E tests for command CRUD, execute, bulk execute, pagination, tags."""

from uuid import uuid4

import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.types import UnvalidatedJsonObject

pytestmark = pytest.mark.docker


def _unwrap_command_id(resp: httpx.Response) -> str:
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        first = data["results"][0]
        return str(first.get("id") or first.get("node_id"))
    return str(data["id"])


def _create_command(
    e2e_client: httpx.Client, **overrides: object
) -> UnvalidatedJsonObject:
    """Helper to create a command template (bulk-first)."""
    data = {
        "name": "e2e-command",
        "command": "echo test",
        "description": "E2E test command",
        **overrides,
    }
    resp = e2e_client.post("/api/v2/commands/", json={"items": [data]})
    assert resp.status_code in (200, 201, 207)
    body = resp.json()
    # Unwrap bulk result to compat dict
    if isinstance(body, dict) and "results" in body:
        first = body["results"][0]
        assert first.get("status") == "success", f"create failed {first}"
        compat: UnvalidatedJsonObject = dict(data)
        compat["id"] = str(first.get("id"))
        compat.update({k: v for k, v in first.items() if k not in compat})
        # Fetch full object to get created_at etc.
        cid = compat["id"]
        get_resp = e2e_client.get(f"/api/v2/commands/{cid}")
        if get_resp.status_code == 200:
            return get_resp.json()
        return compat
    return body


def test_command_crud_full_cycle(e2e_client: httpx.Client) -> None:
    # Create
    cmd = _create_command(e2e_client, name="cmd-create")
    cmd_id = cmd["id"]
    assert cmd["name"] == "cmd-create"
    assert cmd["command"] == "echo test"

    # Read
    resp = e2e_client.get(f"/api/v2/commands/{cmd_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "cmd-create"

    # Read all — CursorPage
    resp = e2e_client.get("/api/v2/commands/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "has_more" in data
    assert "next_cursor" in data
    assert "limit" in data
    assert len(data["items"]) >= 1

    # Update
    resp = e2e_client.patch(
        f"/api/v2/commands/{cmd_id}",
        json={"name": "cmd-updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "cmd-updated"

    # Delete
    resp = e2e_client.delete(f"/api/v2/commands/{cmd_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = e2e_client.get(f"/api/v2/commands/{cmd_id}")
    assert resp.status_code == 404


def test_command_create_with_parameters(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v2/commands/",
        json={
            "items": [
                {
                    "name": "param-cmd",
                    "command": "systemctl restart {service}",
                    "parameters": [
                        {"name": "service", "type": "string", "required": True}
                    ],
                }
            ]
        },
    )
    assert resp.status_code in (200, 201, 207)
    body = resp.json()
    first = body["results"][0] if "results" in body else body
    assert first["status"] == "success"
    cmd_id = first.get("id")
    # Fetch full command to verify parameters
    get_resp = e2e_client.get(f"/api/v2/commands/{cmd_id}")
    assert get_resp.status_code == 200
    cmd = get_resp.json()
    assert cmd["parameters"] is not None
    assert len(cmd["parameters"]) == 1
    assert cmd["parameters"][0]["name"] == "service"
    e2e_client.delete(f"/api/v2/commands/{cmd_id}")


def test_command_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post("/api/v2/commands/", json={"items": [{"name": "no-cmd"}]})
    assert resp.status_code == 422


def test_command_not_found(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())
    resp = e2e_client.get(f"/api/v2/commands/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.patch(f"/api/v2/commands/{fake_id}", json={"name": "x"})
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v2/commands/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Script CRUD
# ---------------------------------------------------------------------------


def test_command_execute_on_node(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="cmd-exec-node")
    cmd = _create_command(e2e_client, name="cmd-exec", command="echo hello-cmd")

    resp = e2e_client.post(
        "/api/v2/commands/executions",
        json={
            "command_ids": [cmd["id"]],
            "node_ids": [node["id"]],
            "params": {cmd["id"]: {}},
        },
    )
    assert resp.status_code in (200, 207)
    result = resp.json()
    assert result["total"] == 1
    assert result["succeeded"] == 1
    assert "hello-cmd" in result["results"][0]["stdout"]
    assert result["results"][0]["exit_code"] == 0


def test_command_execute_not_found(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="cmd-nf-node")
    resp = e2e_client.post(
        "/api/v2/commands/executions",
        json={
            "command_ids": [str(uuid4())],
            "node_ids": [node["id"]],
            "params": {},
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_command_execute_node_not_found(e2e_client: httpx.Client) -> None:
    cmd = _create_command(e2e_client, name="cmd-no-node")
    resp = e2e_client.post(
        "/api/v2/commands/executions",
        json={
            "command_ids": [cmd["id"]],
            "node_ids": [str(uuid4())],
            "params": {cmd["id"]: {}},
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    # Node not found leads to error result, not 404 overall
    assert data["failed"] == 1
    e2e_client.delete(f"/api/v2/commands/{cmd['id']}")


def test_command_execute_missing_required_param(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="cmd-param-node")
    cmd = _create_command(
        e2e_client,
        name="cmd-param",
        command="echo {greeting}",
        parameters=[{"name": "greeting", "type": "string", "required": True}],
    )

    resp = e2e_client.post(
        "/api/v2/commands/executions",
        json={
            "command_ids": [cmd["id"]],
            "node_ids": [node["id"]],
            "params": {cmd["id"]: {}},
        },
    )
    # Missing required param should cause error result, not necessarily 422
    assert resp.status_code in (200, 207, 422)
    if resp.status_code in (200, 207):
        data = resp.json()
        assert data["failed"] == 1


def test_command_execute_with_params(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="cmd-params-node")
    cmd = _create_command(
        e2e_client,
        name="cmd-with-params",
        command="echo {greeting}",
        parameters=[{"name": "greeting", "type": "string", "required": True}],
    )

    resp = e2e_client.post(
        "/api/v2/commands/executions",
        json={
            "command_ids": [cmd["id"]],
            "node_ids": [node["id"]],
            "params": {cmd["id"]: {"greeting": "world"}},
        },
    )
    assert resp.status_code in (200, 207)
    result = resp.json()
    assert result["succeeded"] == 1
    assert result["results"][0]["stdout"].strip() == "world"
    assert result["results"][0]["exit_code"] == 0


# ---------------------------------------------------------------------------
# API key CRUD
# ---------------------------------------------------------------------------


def test_command_pagination(e2e_client: httpx.Client) -> None:
    created: list[str] = []
    for i in range(3):
        cmd = _create_command(e2e_client, name=f"page-cmd-{i}")
        created.append(cmd["id"])

    resp = e2e_client.get("/api/v2/commands/?cursor=&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert "has_more" in data
    assert "next_cursor" in data
    assert data["has_more"] is True
    assert data["limit"] == 2

    for cmd_id in created:
        e2e_client.delete(f"/api/v2/commands/{cmd_id}")


def test_command_partial_update(e2e_client: httpx.Client) -> None:
    cmd = _create_command(e2e_client, name="cmd-partial")

    resp = e2e_client.patch(
        f"/api/v2/commands/{cmd['id']}",
        json={"name": "cmd-partial-updated"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "cmd-partial-updated"
    assert updated["command"] == "echo test"  # unchanged


def test_bulk_execute_by_ids(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node1 = e2e_resources.create_ssh_node(name="bulk-1")
    node2 = e2e_resources.create_ssh_node(name="bulk-2")

    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "commands": ["echo bulk-ok"],
            "node_ids": [node1["id"], node2["id"]],
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0

    node_ids = {r["node_id"] for r in data["results"]}
    assert node1["id"] in node_ids
    assert node2["id"] in node_ids

    for r in data["results"]:
        assert r["stdout"].strip() == "bulk-ok"
        assert r["exit_code"] == 0


def test_bulk_execute_by_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node1 = e2e_resources.create_ssh_node(name="bulk-tag-1", tags=["bulk-test"])
    node2 = e2e_resources.create_ssh_node(name="bulk-tag-2", tags=["bulk-test"])
    e2e_resources.create_ssh_node(name="bulk-tag-other", tags=["other"])

    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"commands": ["echo tagged"], "node_tags": ["bulk-test"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 2
    node_ids = {r["node_id"] for r in data["results"]}
    assert node1["id"] in node_ids
    assert node2["id"] in node_ids


def test_bulk_execute_no_nodes(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"commands": ["echo hi"], "node_ids": [str(uuid4())]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_bulk_execute_partial_failure(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """One good node + one unreachable node = partial success."""
    good_node = e2e_resources.create_ssh_node(name="bulk-good")
    bad_node = e2e_resources.create_node(
        name="bulk-bad",
        host="127.0.0.1",  # closed port — fast connection refused
        port=1,
    )

    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "commands": ["echo partial"],
            "node_ids": [good_node["id"], bad_node["id"]],
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1

    results_by_id = {r["node_id"]: r for r in data["results"]}
    assert results_by_id[good_node["id"]]["exit_code"] == 0
    assert results_by_id[bad_node["id"]]["exit_code"] != 0
    assert results_by_id[bad_node["id"]]["status"] == "error"


def test_bulk_execute_validation_no_targets(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={"commands": ["ls"]},
    )
    # No targets yields either 422 or 200 with error
    assert resp.status_code in (200, 207, 422)
    if resp.status_code in (200, 207):
        data = resp.json()
        assert data["failed"] >= 1 or data["total"] == 0


def test_bulk_execute_validation_empty_command(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "commands": [],
            "node_ids": ["00000000-0000-0000-0000-000000000001"],
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Readiness probe
# ---------------------------------------------------------------------------


def test_command_with_tags(e2e_client: httpx.Client) -> None:
    """Commands can be created with tags and filtered by tag."""
    # Create command with tags
    resp = e2e_client.post(
        "/api/v2/commands/",
        json={
            "items": [
                {
                    "name": "tagged-cmd",
                    "command": "echo tagged",
                    "tags": ["deploy", "prod"],
                }
            ]
        },
    )
    assert resp.status_code in (200, 201, 207)
    body = resp.json()
    first = body["results"][0] if "results" in body else body
    cmd_id = first.get("id")
    # Fetch to verify tags
    get_resp = e2e_client.get(f"/api/v2/commands/{cmd_id}")
    assert get_resp.status_code == 200
    cmd = get_resp.json()
    assert sorted(cmd["tags"]) == ["deploy", "prod"]

    # Filter by tag
    resp = e2e_client.get("/api/v2/commands/?tag=deploy")
    assert resp.status_code == 200
    data = resp.json()
    names = {c["name"] for c in data["items"]}
    assert "tagged-cmd" in names

    # Cleanup
    e2e_client.delete(f"/api/v2/commands/{cmd_id}")
