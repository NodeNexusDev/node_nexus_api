"""E2E tests for X-API-Version header-based API versioning.

Versioning middleware removed in 2.0 (a3f2326) — header is now ignored.
"""

import httpx2 as httpx
import pytest

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]


def test_no_version_header_defaults(e2e_client: httpx.Client) -> None:
    """Missing X-API-Version is accepted (versioning removed in 2.0)."""
    resp = e2e_client.get("/api/v2/nodes/")
    assert resp.status_code == 200
    # X-API-Version header no longer set; accept absent or legacy value
    assert resp.headers.get("X-API-Version") in (None, "1")


def test_explicit_version_header_accepted(e2e_client: httpx.Client) -> None:
    """Explicit X-API-Version is ignored in 2.0."""
    resp = e2e_client.get("/api/v2/nodes/", headers={"X-API-Version": "1"})
    assert resp.status_code == 200
    assert resp.headers.get("X-API-Version") in (None, "1")


def test_unsupported_version_rejected(e2e_client: httpx.Client) -> None:
    """Unsupported X-API-Version is no longer rejected (middleware removed)."""
    resp = e2e_client.get("/api/v2/nodes/", headers={"X-API-Version": "99"})
    # Previously 400, now 200 after removal
    assert resp.status_code == 200
    assert resp.headers.get("X-API-Version") in (None, "1")


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
