"""E2E tests for the dashboard overview endpoint."""

import httpx2 as httpx
import pytest

from tests.e2e.helpers.nodes import wait_for_audit as _wait_for_audit
from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


def test_dashboard_returns_200(e2e_client: httpx.Client) -> None:
    """GET /api/v2/dashboard/ returns a valid response."""
    resp = e2e_client.get("/api/v2/dashboard/")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "scripts" in data
    assert "commands" in data
    assert "docker" in data
    assert "recent_activity" in data


def test_dashboard_counts_nodes(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Dashboard reflects the actual node count."""
    total_before = e2e_client.get("/api/v2/dashboard/").json()["nodes"]["total"]
    e2e_resources.create_node(name="dash-node-1")
    e2e_resources.create_node(name="dash-node-2")

    resp = e2e_client.get("/api/v2/dashboard/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"]["total"] >= total_before + 2


def test_dashboard_counts_scripts(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Dashboard reflects the actual script count."""
    total_before = e2e_client.get("/api/v2/dashboard/").json()["scripts"]["total"]
    e2e_resources.create_script()
    e2e_resources.create_script()

    resp = e2e_client.get("/api/v2/dashboard/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scripts"]["total"] >= total_before + 2


def test_dashboard_counts_commands(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Dashboard reflects the actual command count."""
    total_before = e2e_client.get("/api/v2/dashboard/").json()["commands"]["total"]
    e2e_resources.create_command()
    e2e_resources.create_command()

    resp = e2e_client.get("/api/v2/dashboard/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["commands"]["total"] >= total_before + 2


def test_dashboard_recent_activity(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Dashboard returns recent audit log entries."""
    e2e_resources.create_node(name="dash-activity")
    _wait_for_audit(e2e_client, action="create")

    resp = e2e_client.get("/api/v2/dashboard/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recent_activity"]) >= 1
    # Each entry should have required fields
    entry = data["recent_activity"][0]
    assert "id" in entry
    assert "action" in entry
    assert "created_at" in entry
