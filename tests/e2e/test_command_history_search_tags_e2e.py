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
        f"/api/v1/nodes/{node['id']}/execute",
        json={"command": command_text},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["exit_code"] == 0
    assert "e2e-history-test" in exec_data["stdout"]

    history_resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/commands/history")
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

    search_resp = e2e_client.get("/api/v1/commands/?search=alpha")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert any(item["id"] == command["id"] for item in search_data["items"])

    tag_resp = e2e_client.get(f"/api/v1/commands/?tag={unique_tag}")
    assert tag_resp.status_code == 200
    tag_data = tag_resp.json()
    assert all(unique_tag in item["tags"] for item in tag_data["items"])
    assert any(item["id"] == command["id"] for item in tag_data["items"])

    tags_resp = e2e_client.get("/api/v1/commands/tags")
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

    search_resp = e2e_client.get("/api/v1/scripts/?search=gamma")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert any(item["id"] == script["id"] for item in search_data["items"])

    tag_resp = e2e_client.get(f"/api/v1/scripts/?tag={unique_tag}")
    assert tag_resp.status_code == 200
    tag_data = tag_resp.json()
    assert all(unique_tag in item["tags"] for item in tag_data["items"])
    assert any(item["id"] == script["id"] for item in tag_data["items"])

    tags_resp = e2e_client.get("/api/v1/scripts/tags")
    assert tags_resp.status_code == 200
    assert unique_tag in tags_resp.json()
