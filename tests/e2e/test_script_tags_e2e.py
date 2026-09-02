"""E2E tests for script execution with node_tags support (bulk-first)."""

import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


def test_execute_script_requires_target(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Script execution without node_ids or node_tags returns error result."""
    script = e2e_resources.create_script()
    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={"script_ids": [script["id"]]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_execute_script_with_node_ids(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Script execution with node_ids and missing node returns error result."""
    script = e2e_resources.create_script()
    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={
            "script_ids": [script["id"]],
            "node_ids": ["00000000-0000-0000-0000-000000000000"],
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_execute_script_with_node_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Script execution with node_tags resolves nodes by tag."""
    node = e2e_resources.create_ssh_node(tags=["e2e-target"])
    script = e2e_resources.create_script()

    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={
            "script_ids": [script["id"]],
            "node_tags": ["e2e-target"],
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert len(data["results"]) >= 1
    success = [r for r in data["results"] if r["status"] == "success"]
    assert any(str(r["node_id"]) == node["id"] for r in success)


def test_execute_script_with_node_ids_and_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Script execution with both node_ids and tags uses intersection (AND)."""
    node = e2e_resources.create_ssh_node(tags=["e2e-and"])
    script = e2e_resources.create_script()

    # Intersection: matching ID + matching tag
    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={
            "script_ids": [script["id"]],
            "node_ids": [node["id"]],
            "node_tags": ["e2e-and"],
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["succeeded"] == 1
    assert len(data["results"]) == 1
    assert str(data["results"][0]["node_id"]) == node["id"]


def test_execute_script_with_nonexistent_tags(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Script execution with tags that match no nodes returns error result."""
    script = e2e_resources.create_script()
    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={
            "script_ids": [script["id"]],
            "node_tags": ["nonexistent-tag-xyz"],
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_execute_script_validates_at_least_one_target(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Both node_ids and node_tags empty → error result (no targets)."""
    script = e2e_resources.create_script()
    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={"script_ids": [script["id"]], "node_ids": [], "node_tags": []},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"
