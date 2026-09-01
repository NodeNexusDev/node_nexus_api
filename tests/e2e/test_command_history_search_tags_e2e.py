"""E2E tests for command history, command/script search and tags."""

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker


def test_command_execution_is_recorded_in_history(
    e2e_client: httpx.Client, e2e_resources
) -> None:
    """Executing a command on a node creates a retrievable history record."""
    node = e2e_resources.create_ssh_node()
    command_text = "echo e2e-history-test"

    exec_resp = e2e_client.post(
        "/api/v2/commands/execute",
        json={"node_id": node["id"], "command": command_text},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["exit_code"] == 0
    assert "e2e-history-test" in exec_data["stdout"]

    history_resp = e2e_client.get(
        "/api/v2/commands/history", params={"node_id": node["id"]}
    )
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert history["total"] >= 1
    assert len(history["items"]) >= 1
    latest = history["items"][0]
    assert latest["exit_code"] == 0
    assert latest["command_fingerprint"]
    assert "e2e-history-test" in latest["stdout"]


def test_command_search_and_tags(e2e_client: httpx.Client, e2e_resources) -> None:
    """Commands can be searched by name/description and filtered by tag."""
    unique_tag = e2e_resources.unique_name("e2e-tag")
    command = e2e_resources.create_command(
        name=e2e_resources.unique_name("alpha-search-command"),
        command="echo alpha",
        description="alpha description",
        tags=[unique_tag],
    )
    e2e_resources.create_command(
        name=e2e_resources.unique_name("beta-command"),
        command="echo beta",
        tags=["other"],
    )

    search_resp = e2e_client.get("/api/v2/commands/?search=alpha")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert any(item["id"] == command["id"] for item in search_data["items"])

    tag_resp = e2e_client.get(f"/api/v2/commands/?tag={unique_tag}")
    assert tag_resp.status_code == 200
    tag_data = tag_resp.json()
    assert all(unique_tag in item["tags"] for item in tag_data["items"])
    assert any(item["id"] == command["id"] for item in tag_data["items"])

    tags_resp = e2e_client.get("/api/v2/commands/tags")
    assert tags_resp.status_code == 200
    assert unique_tag in tags_resp.json()


def test_script_search_and_tags(e2e_client: httpx.Client, e2e_resources) -> None:
    """Scripts can be searched by name/description and filtered by tag."""
    unique_tag = e2e_resources.unique_name("e2e-script-tag")
    script = e2e_resources.create_script(
        name=e2e_resources.unique_name("gamma-search-script"),
        description="gamma description",
        tags=[unique_tag],
    )
    e2e_resources.create_script(
        name=e2e_resources.unique_name("delta-script"),
        tags=["other"],
    )

    search_resp = e2e_client.get("/api/v2/scripts/?search=gamma")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert any(item["id"] == script["id"] for item in search_data["items"])

    tag_resp = e2e_client.get(f"/api/v2/scripts/?tag={unique_tag}")
    assert tag_resp.status_code == 200
    tag_data = tag_resp.json()
    assert all(unique_tag in item["tags"] for item in tag_data["items"])
    assert any(item["id"] == script["id"] for item in tag_data["items"])

    tags_resp = e2e_client.get("/api/v2/scripts/tags")
    assert tags_resp.status_code == 200
    assert unique_tag in tags_resp.json()


# ---------------------------------------------------------------------------
# Bulk command history
# ---------------------------------------------------------------------------


def test_bulk_execute_and_history(e2e_client: httpx.Client, e2e_resources) -> None:
    """Bulk execute a command on SSH nodes and retrieve batch history."""
    node1 = e2e_resources.create_ssh_node(name=e2e_resources.unique_name("bulk-1"))
    node2 = e2e_resources.create_ssh_node(name=e2e_resources.unique_name("bulk-2"))

    bulk_resp = e2e_client.post(
        "/api/v2/commands/bulk/execute",
        json={
            "command": "echo bulk-ok",
            "node_ids": [node1["id"], node2["id"]],
        },
    )
    assert bulk_resp.status_code == 200
    bulk_data = bulk_resp.json()
    assert bulk_data["total"] == 2
    assert bulk_data["succeeded"] == 2

    # Verify each node's history
    for node in (node1, node2):
        hist_resp = e2e_client.get(
            "/api/v2/commands/history", params={"node_id": node["id"]}
        )
        assert hist_resp.status_code == 200
        assert hist_resp.json()["total"] >= 1


def test_bulk_history_empty_batch(e2e_client: httpx.Client) -> None:
    """Bulk history for a nonexistent batch_id returns empty list."""
    resp = e2e_client.get(
        "/api/v2/commands/bulk/history",
        params={"batch_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
