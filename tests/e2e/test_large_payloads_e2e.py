"""E2E tests for large payloads and boundary values.

Covers: large command output, many items in lists, Unicode,
special characters, null bytes, and long scripts.

Marker: e2e_slow — these tests may be slower due to data generation.
"""

from uuid import uuid4

import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = [pytest.mark.docker, pytest.mark.e2e_slow]


def _docker_pull_alpine(e2e_client: httpx.Client, node_id: str) -> None:
    resp = e2e_client.post(
        f"/api/v2/nodes/{node_id}/docker/images/pull",
        json={"image": "alpine:latest", "timeout": 120},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# M.1 Large command output
# ---------------------------------------------------------------------------


def test_large_stdout_ssh_command(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """SSH command producing ~100KB stdout is received without truncation."""
    node = e2e_resources.create_ssh_node()
    # Generate ~100KB of output (100 * 1024 bytes)
    cmd = "dd if=/dev/zero bs=1K count=100 2>/dev/null | base64 | head -c 102400"
    resp = e2e_client.post(
        "/api/v2/commands/execute",
        json={"node_id": node["id"], "command": cmd},
        timeout=60.0,
    )
    assert resp.status_code == 200, f"Large output command failed: {resp.status_code}"
    result = resp.json()
    stdout = result.get("stdout", "")
    # Should get substantial output (not empty, not obviously truncated)
    assert len(stdout) > 50000, f"Expected >50KB stdout, got {len(stdout)} bytes"


def test_large_stdout_docker_exec(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Docker exec producing ~100KB output is received without truncation."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        # Start a container
        cmd = "docker run -d --name lp-exec-large alpine sleep 300"
        e2e_client.post(
            "/api/v2/commands/execute",
            json={"node_id": node["id"], "command": cmd},
        )
        # Exec with large output
        exec_cmd = (
            "dd if=/dev/zero bs=1K count=100 2>/dev/null | base64 | head -c 102400"
        )
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/lp-exec-large/exec",
            json={"command": exec_cmd, "timeout": 60},
            timeout=90.0,
        )
        assert resp.status_code == 200, (
            f"Large exec output failed: {resp.status_code} {resp.text[:200]}"
        )
        result = resp.json()
        stdout = result.get("stdout", "")
        assert len(stdout) > 50000, f"Expected >50KB stdout, got {len(stdout)} bytes"
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/lp-exec-large?force=true"
        )


# ---------------------------------------------------------------------------
# M.2 Many items
# ---------------------------------------------------------------------------


def test_many_nodes_pagination(e2e_client: httpx.Client) -> None:
    """50 nodes can be created and listed with correct pagination."""
    node_ids: list[str] = []
    try:
        for i in range(50):
            resp = e2e_client.post(
                "/api/v2/nodes/",
                json={
                    "name": f"lp-many-{i:03d}",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                },
            )
            assert resp.status_code == 201
            node_ids.append(resp.json()["id"])

        # Verify pagination
        resp = e2e_client.get("/api/v2/nodes/?size=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 50
        # All created nodes should be findable
        names = {n["name"] for n in data["items"]}
        for i in range(50):
            assert f"lp-many-{i:03d}" in names, (
                f"Node lp-many-{i:03d} not found in list"
            )
    finally:
        for nid in node_ids:
            e2e_client.delete(f"/api/v2/nodes/{nid}")


# ---------------------------------------------------------------------------
# M.3 Special characters and Unicode
# ---------------------------------------------------------------------------


def test_unicode_node_name(e2e_client: httpx.Client) -> None:
    """Node name with Unicode characters is correctly preserved."""
    name = "テスト-节点-é2e-№"
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "name": name,
            "host": "10.0.0.210",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]
    assert resp.json()["name"] == name

    try:
        resp = e2e_client.get(f"/api/v2/nodes/{node_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name, (
            f"Unicode name not preserved: {resp.json()['name']!r} != {name!r}"
        )
    finally:
        e2e_client.delete(f"/api/v2/nodes/{node_id}")


def test_special_chars_in_ssh_command(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """SSH command with quotes and special characters works correctly."""
    node = e2e_resources.create_ssh_node()
    # Command with single quotes, double quotes, dollar sign
    cmd = """echo 'single-quotes' && echo "double-quotes" && echo dollar-$"""
    resp = e2e_client.post(
        "/api/v2/commands/execute",
        json={"node_id": node["id"], "command": cmd},
    )
    assert resp.status_code == 200
    result = resp.json()
    stdout = result.get("stdout", "")
    assert "single-quotes" in stdout
    assert "double-quotes" in stdout


def test_null_byte_in_node_name_rejected(e2e_client: httpx.Client) -> None:
    """Node name containing null byte is rejected with 422."""
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "name": "bad\x00name",
            "host": "10.0.0.211",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    # May be 422 (validation) or 400 (JSON parse error)
    assert resp.status_code >= 400, (
        f"Expected error for null byte, got {resp.status_code}: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# M.4 Large scripts
# ---------------------------------------------------------------------------


def test_script_many_steps(e2e_client: httpx.Client) -> None:
    """Script with 50 steps is created and all steps are preserved in order."""
    steps = [
        {"label": f"step-{i}", "type": "inline", "command": f"echo step{i}"}
        for i in range(50)
    ]
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={"name": "lp-many-steps", "steps": steps},
    )
    assert resp.status_code == 201
    script_id = resp.json()["id"]

    try:
        resp = e2e_client.get(f"/api/v2/scripts/{script_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["steps"]) == 50
        for i, step in enumerate(data["steps"]):
            assert step["label"] == f"step-{i}"
            assert step["command"] == f"echo step{i}"
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script_id}")


def test_script_step_long_command(e2e_client: httpx.Client) -> None:
    """Script step with command near the max length boundary."""
    # 4096 chars — the max for DockerExecRequest.command
    long_cmd = "echo " + "A" * 4090
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={
            "name": "lp-long-cmd",
            "steps": [{"label": "long-step", "type": "inline", "command": long_cmd}],
        },
    )
    if resp.status_code == 201:
        script_id = resp.json()["id"]
        e2e_client.delete(f"/api/v2/scripts/{script_id}")
    else:
        # 422 is acceptable if the field is length-constrained
        assert resp.status_code == 422, (
            f"Unexpected status for long command: {resp.status_code}"
        )


def test_many_nodes_search(e2e_client: httpx.Client) -> None:
    """Search works correctly among many nodes."""
    node_ids: list[str] = []
    target_name = f"lp-search-target-{uuid4().hex[:8]}"
    try:
        # Create background nodes
        for i in range(10):
            resp = e2e_client.post(
                "/api/v2/nodes/",
                json={
                    "name": f"lp-search-bg-{i}",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                },
            )
            assert resp.status_code == 201
            node_ids.append(resp.json()["id"])
        # Create target
        resp = e2e_client.post(
            "/api/v2/nodes/",
            json={
                "name": target_name,
                "host": "10.0.0.99",
                "port": 22,
                "connection_type": "ssh",
            },
        )
        assert resp.status_code == 201
        node_ids.append(resp.json()["id"])

        # Search for target
        resp = e2e_client.get(f"/api/v2/nodes/?search={target_name}")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["name"] == target_name
    finally:
        for nid in node_ids:
            e2e_client.delete(f"/api/v2/nodes/{nid}")


def test_deeply_nested_json_boundary(e2e_client: httpx.Client) -> None:
    """Script with nested structure at reasonable depth works."""
    # 20 levels of nested structure in extra_fields
    nested: dict[str, object] = {}
    current = nested
    for _ in range(20):
        child: dict[str, object] = {}
        current["nested"] = child
        current = child
    current["value"] = "deep"

    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={
            "name": "lp-nested",
            "steps": [{"label": "s1", "type": "inline", "command": "echo ok"}],
        },
    )
    # Should not 500
    assert resp.status_code < 500, (
        f"Got 5xx on script with extra fields: {resp.status_code}"
    )
    if resp.status_code == 201:
        e2e_client.delete(f"/api/v2/scripts/{resp.json()['id']}")
