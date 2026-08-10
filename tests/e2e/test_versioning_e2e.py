"""E2E tests for X-API-Version header-based API versioning."""

import httpx2 as httpx
import pytest

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]


def test_no_version_header_defaults(e2e_client: httpx.Client) -> None:
    """Missing X-API-Version defaults to version 1."""
    resp = e2e_client.get("/api/v1/nodes/")
    assert resp.status_code == 200
    assert resp.headers["X-API-Version"] == "1"


def test_explicit_version_header_accepted(e2e_client: httpx.Client) -> None:
    """Explicit X-API-Version: 1 is accepted."""
    resp = e2e_client.get("/api/v1/nodes/", headers={"X-API-Version": "1"})
    assert resp.status_code == 200
    assert resp.headers["X-API-Version"] == "1"


def test_unsupported_version_rejected(e2e_client: httpx.Client) -> None:
    """Unsupported X-API-Version returns 400."""
    resp = e2e_client.get("/api/v1/nodes/", headers={"X-API-Version": "99"})
    assert resp.status_code == 400
    assert resp.headers["X-API-Version"] == "1"
    assert "Unsupported API version: 99" in resp.json()["detail"]


def test_version_excluded_from_health(e2e_client: httpx.Client) -> None:
    """Health endpoints are excluded from version enforcement."""
    resp = e2e_client.get("/health", headers={"X-API-Version": "99"})
    assert resp.status_code == 200


def test_version_excluded_from_ready(e2e_client: httpx.Client) -> None:
    """Readiness endpoint is excluded from version enforcement."""
    resp = e2e_client.get("/ready", headers={"X-API-Version": "99"})
    assert resp.status_code == 200


def test_version_excluded_from_metrics(e2e_client: httpx.Client) -> None:
    """Metrics endpoint is excluded from version enforcement."""
    resp = e2e_client.get("/metrics", headers={"X-API-Version": "99"})
    assert resp.status_code == 200
