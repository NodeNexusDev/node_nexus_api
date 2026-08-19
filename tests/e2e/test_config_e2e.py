"""E2E tests for config export/import and atomic rollback."""

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker


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
        assert "passphrase" not in exported
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


def test_config_roundtrip_export_import(e2e_client: httpx.Client) -> None:
    """Export → clear → import → re-export produces equivalent data."""
    # 1. Create test data
    node_resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "rt-node",
            "host": "10.0.0.200",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert node_resp.status_code == 201
    node = node_resp.json()

    cmd_resp = e2e_client.post(
        "/api/v1/commands/",
        json={"name": "rt-cmd", "command": "echo rt"},
    )
    assert cmd_resp.status_code == 201
    cmd = cmd_resp.json()

    try:
        # 2. Export
        export1 = e2e_client.get("/api/v1/config/export").json()
        assert any(n["name"] == "rt-node" for n in export1["nodes"])
        assert any(c["name"] == "rt-cmd" for c in export1["commands"])

        # 3. Delete test data
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")
        e2e_client.delete(f"/api/v1/commands/{cmd['id']}")

        # 4. Import back
        import_payload = {
            "nodes": [n for n in export1["nodes"] if n["name"] == "rt-node"],
            "commands": [c for c in export1["commands"] if c["name"] == "rt-cmd"],
            "scripts": [],
        }
        import_resp = e2e_client.post("/api/v1/config/import", json=import_payload)
        assert import_resp.status_code == 200
        result = import_resp.json()
        assert result["nodes_created"] >= 1
        assert result["commands_created"] >= 1

        # 5. Re-export and verify
        export2 = e2e_client.get("/api/v1/config/export").json()
        assert any(n["name"] == "rt-node" for n in export2["nodes"])
        assert any(c["name"] == "rt-cmd" for c in export2["commands"])

        # 6. Cleanup re-imported data
        nodes_resp = e2e_client.get("/api/v1/nodes/")
        for n in nodes_resp.json()["items"]:
            if n["name"] == "rt-node":
                e2e_client.delete(f"/api/v1/nodes/{n['id']}")
        cmds_resp = e2e_client.get("/api/v1/commands/")
        for c in cmds_resp.json()["items"]:
            if c["name"] == "rt-cmd":
                e2e_client.delete(f"/api/v1/commands/{c['id']}")
    finally:
        # Ensure cleanup in case of mid-test failure
        nodes_resp = e2e_client.get("/api/v1/nodes/")
        for n in nodes_resp.json()["items"]:
            if n["name"] == "rt-node":
                e2e_client.delete(f"/api/v1/nodes/{n['id']}")
        cmds_resp = e2e_client.get("/api/v1/commands/")
        for c in cmds_resp.json()["items"]:
            if c["name"] == "rt-cmd":
                e2e_client.delete(f"/api/v1/commands/{c['id']}")


def test_config_import_atomic_rollback(e2e_client: httpx.Client) -> None:
    """Invalid item in import payload causes atomic rollback — no partial data."""
    # Count existing nodes before import
    before = e2e_client.get("/api/v1/nodes/").json()["total"]

    # Payload: one valid node, one invalid (missing required fields)
    resp = e2e_client.post(
        "/api/v1/config/import",
        json={
            "nodes": [
                {
                    "name": "atomic-good",
                    "host": "10.0.0.201",
                    "port": 22,
                    "connection_type": "ssh",
                },
                {"name": "atomic-bad"},  # Missing host, port, connection_type
            ]
        },
    )
    # Should fail — either validation error or import error
    assert resp.status_code >= 400, (
        f"Expected error status, got {resp.status_code}: {resp.text}"
    )

    # Verify no nodes were created
    after = e2e_client.get("/api/v1/nodes/").json()["total"]
    assert after == before, (
        f"Atomicity violation: {after - before} nodes leaked despite import error"
    )

    # Also verify "atomic-good" was NOT created
    nodes = e2e_client.get("/api/v1/nodes/").json()["items"]
    assert not any(n["name"] == "atomic-good" for n in nodes), (
        "Partial import: 'atomic-good' node was created despite payload error"
    )


def test_config_import_invalid_uuid(e2e_client: httpx.Client) -> None:
    """Import with invalid UUID reference: API accepts or rejects gracefully."""

    resp = e2e_client.post(
        "/api/v1/config/import",
        json={
            "nodes": [
                {
                    "id": "not-a-valid-uuid",
                    "name": "bad-uuid-node",
                    "host": "10.0.0.202",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    # The API may accept the import (ignoring invalid id) with 200,
    # or reject it — both are valid. Key assertion: no 500 error.
    assert resp.status_code < 500, (
        f"Got 5xx on invalid UUID import: {resp.status_code} {resp.text}"
    )

    # Cleanup if node was created
    after = e2e_client.get("/api/v1/nodes/").json()
    for n in after["items"]:
        if n["name"] == "bad-uuid-node":
            e2e_client.delete(f"/api/v1/nodes/{n['id']}")


def test_config_import_unsupported_version(e2e_client: httpx.Client) -> None:
    """Import with unsupported version does not change DB."""
    before_nodes = e2e_client.get("/api/v1/nodes/").json()["total"]
    before_cmds = e2e_client.get("/api/v1/commands/").json()["total"]

    resp = e2e_client.post(
        "/api/v1/config/import",
        json={
            "version": 999,
            "nodes": [
                {
                    "name": "v999-node",
                    "host": "10.0.0.203",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ],
        },
    )
    # Should error due to unsupported version
    assert resp.status_code >= 400, (
        f"Expected error for unsupported version, got {resp.status_code}: {resp.text}"
    )

    after_nodes = e2e_client.get("/api/v1/nodes/").json()["total"]
    after_cmds = e2e_client.get("/api/v1/commands/").json()["total"]
    assert after_nodes == before_nodes, "Nodes changed despite unsupported version"
    assert after_cmds == before_cmds, "Commands changed despite unsupported version"


# ---------------------------------------------------------------------------
# Dry-run import
# ---------------------------------------------------------------------------


def test_config_import_dry_run(e2e_client: httpx.Client) -> None:
    """POST /api/v1/config/import with dry_run=true returns preview without writing."""
    before_nodes = e2e_client.get("/api/v1/nodes/").json()["total"]

    resp = e2e_client.post(
        "/api/v1/config/import",
        json={
            "dry_run": True,
            "nodes": [
                {
                    "name": "dry-node",
                    "host": "10.0.0.60",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ],
            "commands": [{"name": "dry-cmd", "command": "echo dry"}],
            "scripts": [{"name": "dry-script", "steps": []}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert len(data["would_create"]["nodes"]) == 1
    assert data["would_create"]["nodes"][0]["name"] == "dry-node"
    assert len(data["would_create"]["commands"]) == 1
    assert data["would_create"]["commands"][0]["name"] == "dry-cmd"
    assert len(data["would_create"]["scripts"]) == 1
    assert data["would_create"]["scripts"][0]["name"] == "dry-script"
    assert data["duplicates"] == []
    assert data["errors"] == []

    # Verify nothing was actually created
    after_nodes = e2e_client.get("/api/v1/nodes/").json()["total"]
    assert after_nodes == before_nodes


def test_config_import_dry_run_reports_duplicates(e2e_client: httpx.Client) -> None:
    """Dry-run reports existing items as duplicates without writing."""
    # Create a node first
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "dry-dup-node",
            "host": "10.0.0.61",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    try:
        resp = e2e_client.post(
            "/api/v1/config/import",
            json={
                "dry_run": True,
                "nodes": [
                    {
                        "name": "dry-dup-node",
                        "host": "10.0.0.61",
                        "port": 22,
                        "connection_type": "ssh",
                    },
                    {
                        "name": "dry-new-node",
                        "host": "10.0.0.62",
                        "port": 22,
                        "connection_type": "ssh",
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        # Only the new node would be created
        assert len(data["would_create"]["nodes"]) == 1
        assert data["would_create"]["nodes"][0]["name"] == "dry-new-node"
        # Existing node reported as duplicate
        assert len(data["duplicates"]) == 1
        assert "dry-dup-node" in data["duplicates"][0]
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node_id}")


def test_config_import_dry_run_unsupported_version(e2e_client: httpx.Client) -> None:
    """Dry-run still rejects unsupported format versions."""
    resp = e2e_client.post(
        "/api/v1/config/import",
        json={
            "dry_run": True,
            "format_version": "99.0",
            "nodes": [
                {
                    "name": "dry-v99",
                    "host": "10.0.0.63",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ],
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Script scheduling
# ---------------------------------------------------------------------------
