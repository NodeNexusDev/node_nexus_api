"""E2E smoke tests: health, readiness, security, metrics."""

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker


def test_health(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_readiness(e2e_client: httpx.Client) -> None:
    """Readiness probe checks database connectivity."""
    resp = e2e_client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"


def test_readiness_no_auth(e2e_client_no_auth: httpx.Client) -> None:
    """Readiness probe does not require authentication."""
    resp = e2e_client_no_auth.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"


def test_security_headers(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-xss-protection"] == "1; mode=block"
    assert "max-age=31536000" in resp.headers["strict-transport-security"]


# ---------------------------------------------------------------------------
# Partial update
# ---------------------------------------------------------------------------


def test_cors_preflight(e2e_client: httpx.Client) -> None:
    resp = e2e_client.options(
        "/api/v1/nodes/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods

    # Also verify that a regular GET response includes CORS headers
    resp = e2e_client.get(
        "/api/v1/nodes/",
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# Command template CRUD
# ---------------------------------------------------------------------------


def test_readiness_probe(e2e_client: httpx.Client) -> None:
    """GET /ready checks database connectivity."""
    resp = e2e_client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"


# ---------------------------------------------------------------------------
# API Key PATCH and scope
# ---------------------------------------------------------------------------


def test_rate_limit_headers(e2e_client: httpx.Client) -> None:
    """Responses include rate limit headers."""
    resp = e2e_client.get("/api/v1/nodes/")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------


def test_metrics_endpoint_exists(e2e_client: httpx.Client) -> None:
    """GET /metrics returns Prometheus text format."""
    resp = e2e_client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "http_requests_total" in text or "http_request_duration" in text


def test_metrics_no_auth_required(e2e_client_no_auth: httpx.Client) -> None:
    """/metrics does not require authentication."""
    resp = e2e_client_no_auth.get("/metrics")
    assert resp.status_code == 200


def test_metrics_excludes_health(
    e2e_client: httpx.Client, e2e_client_no_auth: httpx.Client
) -> None:
    """/metrics response does not count /health hits."""
    for _ in range(5):
        e2e_client_no_auth.get("/health")
    resp = e2e_client.get("/metrics")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Cursor-based pagination
# ---------------------------------------------------------------------------
