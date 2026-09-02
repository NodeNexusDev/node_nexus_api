"""E2E tests for node credential validation (bulk-first)."""

import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


def test_validate_credentials_success(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """POST /api/v2/nodes/credential-validations returns success for valid SSH."""
    node = e2e_resources.create_ssh_node(name="cred-valid")
    resp = e2e_client.post(
        "/api/v2/nodes/credential-validations",
        json={"ids": [node["id"]]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    result = data["results"][0]
    assert result["status"] == "success"
    assert result["node_id"] == node["id"]


def test_validate_credentials_failure(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Returns error for bad credentials via bulk credential-validations."""
    node = e2e_resources.create_ssh_node(
        name="cred-bad", username="wrong-user", password="wrong-pass"
    )
    resp = e2e_client.post(
        "/api/v2/nodes/credential-validations",
        json={"ids": [node["id"]]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_validate_credentials_connection_refused(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Returns error for unreachable host via bulk credential-validations."""
    node = e2e_resources.create_node(
        name="cred-unreach",
        host="192.0.2.1",
        port=19999,
        username="testuser",
        password="testpass",
    )
    resp = e2e_client.post(
        "/api/v2/nodes/credential-validations",
        json={"ids": [node["id"]]},
        timeout=60.0,
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["results"][0]["status"] == "error"


def test_validate_credentials_validation_error(e2e_client: httpx.Client) -> None:
    """POST /api/v2/nodes/credential-validations returns 422 for invalid input."""
    # Empty ids list triggers min_length validation (bulk-first)
    resp = e2e_client.post(
        "/api/v2/nodes/credential-validations",
        json={"ids": []},
    )
    assert resp.status_code == 422
