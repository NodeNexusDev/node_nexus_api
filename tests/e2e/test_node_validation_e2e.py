"""E2E tests for node credential validation."""

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker


def test_validate_credentials_success(e2e_client: httpx.Client) -> None:
    """POST /api/v1/nodes/validate-credentials returns active for valid SSH."""
    resp = e2e_client.post(
        "/api/v1/nodes/validate-credentials",
        json={
            "host": "ssh-server",
            "port": 2222,
            "username": "testuser",
            "password": "testpass",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert "successful" in data["message"].lower()


def test_validate_credentials_failure(
    e2e_client: httpx.Client,
) -> None:
    """Returns unreachable for bad credentials."""
    resp = e2e_client.post(
        "/api/v1/nodes/validate-credentials",
        json={
            "host": "ssh-server",
            "port": 2222,
            "username": "wrong-user",
            "password": "wrong-pass",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unreachable"


def test_validate_credentials_connection_refused(
    e2e_client: httpx.Client,
) -> None:
    """Returns unreachable for unreachable host."""
    resp = e2e_client.post(
        "/api/v1/nodes/validate-credentials",
        json={
            "host": "192.0.2.1",
            "port": 19999,
            "username": "testuser",
            "password": "testpass",
        },
        timeout=60.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unreachable"


def test_validate_credentials_validation_error(e2e_client: httpx.Client) -> None:
    """POST /api/v1/nodes/validate-credentials returns 422 for invalid input."""
    resp = e2e_client.post(
        "/api/v1/nodes/validate-credentials",
        json={},
    )
    assert resp.status_code == 422
