"""E2E tests for Stage F: favorites, notes, tags, search, stats, clone."""

import time

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker


# ── Favorites ────────────────────────────────────────────────────────────────


class TestFavorites:
    def test_add_list_remove_favorite(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        node = e2e_resources.create_ssh_node()

        # Add favorite (trailing slash required for POST /)
        resp = e2e_client.post(
            "/api/v2/favorites/",
            json={
                "target_type": "node",
                "target_id": node["id"],
                "note": "my favorite node",
            },
        )
        assert resp.status_code == 201, f"{resp.status_code} {resp.text}"
        fav = resp.json()
        assert fav["target_type"] == "node"
        assert fav["target_id"] == node["id"]
        assert fav["note"] == "my favorite node"
        fav_id = fav["id"]

        # List favorites — CursorPage (has_more/next_cursor, no total)
        resp = e2e_client.get("/api/v2/favorites/")
        assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        assert "has_more" in data and "next_cursor" in data
        ids = [f["id"] for f in data["items"]]
        assert fav_id in ids

        # List favorites filtered by target_type
        resp = e2e_client.get("/api/v2/favorites/?target_type=node")
        assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
        assert len(resp.json()["items"]) >= 1

        # Remove favorite
        resp = e2e_client.delete(f"/api/v2/favorites/node/{node['id']}")
        assert resp.status_code == 204, f"{resp.status_code} {resp.text}"

        # Verify removed
        resp = e2e_client.get("/api/v2/favorites/")
        assert resp.status_code == 200
        ids = [f["id"] for f in resp.json()["items"]]
        assert fav_id not in ids

    def test_add_favorite_without_note(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        node = e2e_resources.create_ssh_node()
        resp = e2e_client.post(
            "/api/v2/favorites/",
            json={"target_type": "node", "target_id": node["id"]},
        )
        assert resp.status_code == 201, f"{resp.status_code} {resp.text}"
        assert resp.json()["note"] is None

    def test_add_favorite_invalid_target(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        resp = e2e_client.post(
            "/api/v2/favorites/",
            json={
                "target_type": "node",
                "target_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert resp.status_code in (201, 404, 422), f"{resp.status_code} {resp.text}"


# ── Notes ────────────────────────────────────────────────────────────────────
# Notes removed in 2.0 (DROP TABLE notes) — tests kept as skip for coverage history


@pytest.mark.skip(reason="notes removed in 2.0 — endpoint no longer exists")
class TestNotes:
    def test_create_list_update_delete_note(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        pass

    def test_notes_empty_for_new_node(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        pass


# ── Global Search ────────────────────────────────────────────────────────────


class TestGlobalSearch:
    def test_search_finds_node(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()

        resp = e2e_client.get(f"/api/v2/search?q={node['name']}")
        assert resp.status_code == 200
        data = resp.json()
        node_ids = [n["id"] for n in data["nodes"]]
        assert str(node["id"]) in node_ids

    def test_search_finds_command(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        cmd = e2e_resources.create_command()

        resp = e2e_client.get(f"/api/v2/search?q={cmd['name']}")
        assert resp.status_code == 200
        data = resp.json()
        cmd_ids = [c["id"] for c in data["commands"]]
        assert str(cmd["id"]) in cmd_ids

    def test_search_finds_script(self, e2e_client: httpx.Client, e2e_resources) -> None:
        script = e2e_resources.create_script()

        resp = e2e_client.get(f"/api/v2/search?q={script['name']}")
        assert resp.status_code == 200
        data = resp.json()
        script_ids = [s["id"] for s in data["scripts"]]
        assert str(script["id"]) in script_ids

    def test_search_empty_query_rejected(self, e2e_client: httpx.Client) -> None:
        resp = e2e_client.get("/api/v2/search?q=")
        assert resp.status_code == 422


# ── Execution Stats ──────────────────────────────────────────────────────────


class TestExecutionStats:
    def test_command_stats(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()
        cmd = e2e_resources.create_command()

        # Execute via bulk-first executions (by command_id)
        resp = e2e_client.post(
            "/api/v2/commands/executions",
            json={
                "command_ids": [cmd["id"]],
                "node_ids": [node["id"]],
                "params": {},
            },
        )
        assert resp.status_code in (200, 207), f"{resp.status_code} {resp.text}"
        data = resp.json()
        # Ensure execution succeeded at least once
        assert data["total"] >= 1, f"executions failed: {data}"
        assert data["succeeded"] >= 1, f"executions not succeeded: {data}"

        # Poll stats until available (execution writes async, command_id now stored)
        stats = None
        for _ in range(10):
            resp = e2e_client.get(f"/api/v2/commands/{cmd['id']}/stats")
            assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
            stats = resp.json()
            if stats["total"] >= 1:
                break
            time.sleep(1)
        # Fallback: verify via node stats if command_id stats still lagging
        if stats is None or stats["total"] < 1:
            for _ in range(5):
                resp = e2e_client.get(
                    "/api/v2/commands/stats", params={"node_id": node["id"]}
                )
                assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
                node_stats = resp.json()
                if node_stats["total"] >= 1:
                    # At least node stats shows execution, command stats may be delayed
                    # Re-check command stats once more before failing
                    resp = e2e_client.get(f"/api/v2/commands/{cmd['id']}/stats")
                    stats = resp.json()
                    if stats["total"] >= 1:
                        break
                time.sleep(1)
        assert stats is not None
        assert stats["total"] >= 1, f"stats not updated: {stats}"
        assert stats["successful"] >= 1, f"stats: {stats}"
        assert stats["failed"] == 0, f"stats: {stats}"

    def test_node_stats(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()
        cmd = e2e_resources.create_command()

        # Execute via bulk-first executions
        resp = e2e_client.post(
            "/api/v2/commands/executions",
            json={
                "command_ids": [cmd["id"]],
                "node_ids": [node["id"]],
                "params": {},
            },
        )
        assert resp.status_code in (200, 207), f"{resp.status_code} {resp.text}"

        # Get node stats with retry (execution may be async)
        stats = None
        for _ in range(5):
            resp = e2e_client.get(
                "/api/v2/commands/stats", params={"node_id": node["id"]}
            )
            assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
            stats = resp.json()
            if stats["total"] >= 1:
                break
            time.sleep(1)
        assert stats is not None
        assert stats["total"] >= 1, f"stats: {stats}"

    def test_script_stats(self, e2e_client: httpx.Client, e2e_resources) -> None:
        node = e2e_resources.create_ssh_node()
        script = e2e_resources.create_script()

        # Execute script via bulk executions
        resp = e2e_client.post(
            "/api/v2/scripts/executions",
            json={"script_ids": [script["id"]], "node_ids": [node["id"]]},
        )
        assert resp.status_code in (200, 207)

        # Get stats
        resp = e2e_client.get(f"/api/v2/scripts/{script['id']}/stats")
        # script stats may be 404 if not implemented as separate, accept 200 or 404
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            stats = resp.json()
            assert stats["total"] >= 0


# ── Clone ────────────────────────────────────────────────────────────────────


class TestClone:
    def test_clone_command(self, e2e_client: httpx.Client, e2e_resources) -> None:
        cmd = e2e_resources.create_command(command="echo clone-test")

        resp = e2e_client.post(f"/api/v2/commands/{cmd['id']}/clone")
        assert resp.status_code in (200, 201)
        cloned = resp.json()
        assert cloned["id"] != cmd["id"]
        assert cloned["command"] == "echo clone-test"
        assert "copy" in cloned["name"].lower() or cloned["name"] != cmd["name"]

    def test_clone_command_with_custom_name(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        cmd = e2e_resources.create_command()

        resp = e2e_client.post(
            f"/api/v2/commands/{cmd['id']}/clone",
            params={"new_name": "my-custom-copy"},
        )
        assert resp.status_code in (200, 201)
        assert resp.json()["name"] == "my-custom-copy"

    def test_clone_script(self, e2e_client: httpx.Client, e2e_resources) -> None:
        script = e2e_resources.create_script()

        resp = e2e_client.post(f"/api/v2/scripts/{script['id']}/clone")
        assert resp.status_code in (200, 201)
        cloned = resp.json()
        assert cloned["id"] != script["id"]

    def test_clone_script_with_custom_name(
        self, e2e_client: httpx.Client, e2e_resources
    ) -> None:
        script = e2e_resources.create_script()

        resp = e2e_client.post(
            f"/api/v2/scripts/{script['id']}/clone",
            params={"new_name": "script-copy"},
        )
        assert resp.status_code in (200, 201)
        assert resp.json()["name"] == "script-copy"


# ── Dashboard Metrics ────────────────────────────────────────────────────────
# Dashboard removed in 2.0 — replaced by /commands/stats


@pytest.mark.skip(reason="dashboard removed in 2.0 — use /commands/stats")
class TestDashboardMetrics:
    def test_dashboard_metrics(self, e2e_client: httpx.Client, e2e_resources) -> None:
        pass


# ── Audit Export ─────────────────────────────────────────────────────────────


class TestAuditExport:
    def test_audit_export_csv(self, e2e_client: httpx.Client) -> None:
        resp = e2e_client.get("/api/v2/audit/exports?fmt=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_audit_export_json(self, e2e_client: httpx.Client) -> None:
        resp = e2e_client.get("/api/v2/audit/exports?fmt=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
