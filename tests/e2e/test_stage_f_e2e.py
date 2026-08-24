"""E2E tests for Stage F: favorites, notes, tags, search, stats, clone."""

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker


# ── Favorites ────────────────────────────────────────────────────────────────


class TestFavorites:
    def test_add_list_remove_favorite(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        node = e2e_resources.create_ssh_node()

        # Add favorite
        resp = e2e_client.post(
            "/api/v1/favorites",
            json={
                "target_type": "node",
                "target_id": node["id"],
                "note": "my favorite node",
            },
        )
        assert resp.status_code == 201
        fav = resp.json()
        assert fav["target_type"] == "node"
        assert fav["target_id"] == node["id"]
        assert fav["note"] == "my favorite node"
        fav_id = fav["id"]

        # List favorites
        resp = e2e_client.get("/api/v1/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        ids = [f["id"] for f in data["items"]]
        assert fav_id in ids

        # List favorites filtered by target_type
        resp = e2e_client.get("/api/v1/favorites?target_type=node")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        # Remove favorite
        resp = e2e_client.delete(f"/api/v1/favorites/node/{node['id']}")
        assert resp.status_code == 204

        # Verify removed
        resp = e2e_client.get("/api/v1/favorites")
        assert resp.status_code == 200
        ids = [f["id"] for f in resp.json()["items"]]
        assert fav_id not in ids

    def test_add_favorite_without_note(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        node = e2e_resources.create_ssh_node()
        resp = e2e_client.post(
            "/api/v1/favorites",
            json={"target_type": "node", "target_id": node["id"]},
        )
        assert resp.status_code == 201
        assert resp.json()["note"] is None

    def test_add_favorite_invalid_target(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        resp = e2e_client.post(
            "/api/v1/favorites",
            json={
                "target_type": "node",
                "target_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert resp.status_code in (201, 404)


# ── Notes ────────────────────────────────────────────────────────────────────


class TestNotes:
    def test_create_list_update_delete_note(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        node = e2e_resources.create_ssh_node()

        # Create note
        resp = e2e_client.post(
            f"/api/v1/notes/node/{node['id']}",
            json={
                "target_type": "node",
                "target_id": node["id"],
                "content": "First note",
            },
        )
        assert resp.status_code == 201
        note = resp.json()
        assert note["content"] == "First note"
        assert note["target_type"] == "node"
        note_id = note["id"]

        # Create second note
        resp = e2e_client.post(
            f"/api/v1/notes/node/{node['id']}",
            json={
                "target_type": "node",
                "target_id": node["id"],
                "content": "Second note",
            },
        )
        assert resp.status_code == 201

        # List notes
        resp = e2e_client.get(f"/api/v1/notes/node/{node['id']}")
        assert resp.status_code == 200
        notes = resp.json()
        assert len(notes) == 2

        # Update note
        resp = e2e_client.put(
            f"/api/v1/notes/{note_id}",
            json={"content": "Updated content"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "Updated content"

        # Delete note
        resp = e2e_client.delete(f"/api/v1/notes/{note_id}")
        assert resp.status_code == 204

        # Verify deleted
        resp = e2e_client.get(f"/api/v1/notes/node/{node['id']}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_notes_empty_for_new_node(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        node = e2e_resources.create_ssh_node()
        resp = e2e_client.get(f"/api/v1/notes/node/{node['id']}")
        assert resp.status_code == 200
        assert resp.json() == []


# ── Global Search ────────────────────────────────────────────────────────────


class TestGlobalSearch:
    def test_search_finds_node(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()

        resp = e2e_client.get(f"/api/v1/search?q={node['name']}")
        assert resp.status_code == 200
        data = resp.json()
        node_ids = [n["id"] for n in data["nodes"]]
        assert str(node["id"]) in node_ids

    def test_search_finds_command(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        cmd = e2e_resources.create_command()

        resp = e2e_client.get(f"/api/v1/search?q={cmd['name']}")
        assert resp.status_code == 200
        data = resp.json()
        cmd_ids = [c["id"] for c in data["commands"]]
        assert str(cmd["id"]) in cmd_ids

    def test_search_finds_script(self, e2e_client: httpx.Client, e2e_resources) -> None:
        script = e2e_resources.create_script()

        resp = e2e_client.get(f"/api/v1/search?q={script['name']}")
        assert resp.status_code == 200
        data = resp.json()
        script_ids = [s["id"] for s in data["scripts"]]
        assert str(script["id"]) in script_ids

    def test_search_empty_query_rejected(self, e2e_client: httpx.Client) -> None:
        resp = e2e_client.get("/api/v1/search?q=")
        assert resp.status_code == 422


# ── Execution Stats ──────────────────────────────────────────────────────────


class TestExecutionStats:
    def test_command_stats(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()
        cmd = e2e_resources.create_command()

        # Execute command first
        resp = e2e_client.post(
            f"/api/v1/commands/{cmd['id']}/execute",
            json={"node_id": node["id"]},
        )
        assert resp.status_code == 200

        # Get stats
        resp = e2e_client.get(f"/api/v1/commands/{cmd['id']}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total"] >= 1
        assert stats["successful"] >= 0

    def test_node_stats(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()
        cmd = e2e_resources.create_command()

        # Execute command on node
        resp = e2e_client.post(
            f"/api/v1/commands/{cmd['id']}/execute",
            json={"node_id": node["id"]},
        )
        assert resp.status_code == 200

        # Get node stats
        resp = e2e_client.get(
            "/api/v1/commands/stats", params={"node_id": node["id"]}
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total"] >= 1

    def test_script_stats(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()
        script = e2e_resources.create_script()

        # Execute script
        resp = e2e_client.post(
            f"/api/v1/scripts/{script['id']}/execute",
            json={"node_ids": [node["id"]]},
        )
        assert resp.status_code == 200

        # Get stats
        resp = e2e_client.get(f"/api/v1/scripts/{script['id']}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total"] >= 1


# ── Clone ────────────────────────────────────────────────────────────────────


class TestClone:
    def test_clone_command(self, e2e_client: httpx.Client, e2e_resources) -> None:
        cmd = e2e_resources.create_command(command="echo clone-test")

        resp = e2e_client.post(f"/api/v1/commands/{cmd['id']}/clone")
        assert resp.status_code == 200
        cloned = resp.json()
        assert cloned["id"] != cmd["id"]
        assert cloned["command"] == "echo clone-test"
        assert "copy" in cloned["name"].lower() or cloned["name"] != cmd["name"]

    def test_clone_command_with_custom_name(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        cmd = e2e_resources.create_command()

        resp = e2e_client.post(
            f"/api/v1/commands/{cmd['id']}/clone",
            params={"new_name": "my-custom-copy"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-custom-copy"

    def test_clone_script(self, e2e_client: httpx.Client, e2e_resources) -> None:
        script = e2e_resources.create_script()

        resp = e2e_client.post(f"/api/v1/scripts/{script['id']}/clone")
        assert resp.status_code == 200
        cloned = resp.json()
        assert cloned["id"] != script["id"]

    def test_clone_script_with_custom_name(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        script = e2e_resources.create_script()

        resp = e2e_client.post(
            f"/api/v1/scripts/{script['id']}/clone",
            params={"new_name": "script-copy"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "script-copy"


# ── Dashboard Metrics ────────────────────────────────────────────────────────


class TestDashboardMetrics:
    def test_dashboard_metrics(self, e2e_client: httpx.Client, e2e_resources) -> None:
        # Execute something to generate metrics
        node = e2e_resources.create_ssh_node()
        cmd = e2e_resources.create_command()
        e2e_client.post(
            f"/api/v1/commands/{cmd['id']}/execute",
            json={"node_id": node["id"]},
        )

        resp = e2e_client.get("/api/v1/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "command_metrics" in data
        assert "script_metrics" in data


# ── Audit Export ─────────────────────────────────────────────────────────────


class TestAuditExport:
    def test_audit_export_csv(self, e2e_client: httpx.Client) -> None:
        resp = e2e_client.get("/api/v1/audit/export?fmt=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_audit_export_json(self, e2e_client: httpx.Client) -> None:
        resp = e2e_client.get("/api/v1/audit/export?fmt=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
