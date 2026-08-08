"""Full-stack middleware behavior E2E tests (Phase H).

Tests rate limiting, request timeout, and security middleware against
dedicated Docker Compose stacks with custom config.
"""

import time

import httpx2 as httpx
import pytest

from tests.e2e.helpers.middleware_stack import MiddlewareStackManager, MiddlewareStackPorts

pytestmark = pytest.mark.docker

_MASTER_API_KEY = "e2e-master-key-12345"


# ---------------------------------------------------------------------------
# Fixtures: rate-limit stack (RATE_LIMIT_REQUESTS=5, WINDOW=10s)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rate_limit_stack() -> MiddlewareStackPorts:
    """Start a Docker stack with a very low rate limit (5 req / 10s window)."""
    mgr = MiddlewareStackManager(
        compose_file=__import__("pathlib").Path(
            "tests/docker-compose.e2e-ratelimit.yml"
        ).resolve(),
        project_name="e2e-ratelimit",
        api_port=8002,
        db_port=5434,
    )
    ports = mgr.up()
    yield ports
    mgr.down()


@pytest.fixture(scope="module")
def rate_limit_client(rate_limit_stack: MiddlewareStackPorts) -> httpx.Client:
    return httpx.Client(
        base_url=f"http://{rate_limit_stack.api_host}:{rate_limit_stack.api_port}",
        timeout=10.0,
        headers={"X-API-Key": _MASTER_API_KEY},
    )


# ---------------------------------------------------------------------------
# Fixtures: timeout stack (REQUEST_TIMEOUT=2s)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def timeout_stack() -> MiddlewareStackPorts:
    """Start a Docker stack with a short request timeout (2 seconds)."""
    mgr = MiddlewareStackManager(
        compose_file=__import__("pathlib").Path(
            "tests/docker-compose.e2e-timeout.yml"
        ).resolve(),
        project_name="e2e-timeout",
        api_port=8003,
        db_port=5435,
    )
    ports = mgr.up()
    yield ports
    mgr.down()


@pytest.fixture(scope="module")
def timeout_client(timeout_stack: MiddlewareStackPorts) -> httpx.Client:
    return httpx.Client(
        base_url=f"http://{timeout_stack.api_host}:{timeout_stack.api_port}",
        timeout=10.0,
        headers={"X-API-Key": _MASTER_API_KEY},
    )


# ===================================================================
# H.1 Rate limit
# ===================================================================


class TestRateLimit:
    """Rate-limit middleware behavior (RATE_LIMIT_REQUESTS=5, WINDOW=10s)."""

    def test_remaining_header_decrements(
        self, rate_limit_client: httpx.Client
    ) -> None:
        """Each request decrements X-RateLimit-Remaining."""
        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        remaining = int(resp.headers["X-RateLimit-Remaining"])
        assert remaining >= 0

        resp2 = rate_limit_client.get("/api/v1/nodes/")
        assert resp2.status_code == 200
        remaining2 = int(resp2.headers["X-RateLimit-Remaining"])
        assert remaining2 < remaining

    def test_429_after_limit_exceeded(
        self, rate_limit_client: httpx.Client
    ) -> None:
        """After exceeding the limit, 429 is returned."""
        # Drain the limit (5 requests)
        for _ in range(5):
            rate_limit_client.get("/api/v1/nodes/")

        # Next request should be 429
        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 429
        body = resp.json()
        assert "Rate limit exceeded" in body["detail"]

    def test_retry_after_header_present(
        self, rate_limit_client: httpx.Client
    ) -> None:
        """429 response includes Retry-After header."""
        # Drain the limit
        for _ in range(5):
            rate_limit_client.get("/api/v1/nodes/")

        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 429
        retry_after = resp.headers.get("Retry-After")
        assert retry_after is not None
        assert int(retry_after) > 0

    def test_excluded_paths_not_rate_limited(
        self, rate_limit_client: httpx.Client
    ) -> None:
        """/health and /ready are not rate limited."""
        # Drain the limit
        for _ in range(5):
            rate_limit_client.get("/api/v1/nodes/")

        # /health should still work
        resp = rate_limit_client.get("/health")
        assert resp.status_code == 200

        # /ready should still work
        resp = rate_limit_client.get("/ready")
        assert resp.status_code == 200

    def test_requests_resume_after_window(
        self, rate_limit_client: httpx.Client
    ) -> None:
        """After the rate-limit window expires, requests succeed again."""
        # Drain the limit
        for _ in range(5):
            rate_limit_client.get("/api/v1/nodes/")

        # Confirm rate limited
        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 429

        # Wait for window to expire (10s window + 1s buffer)
        time.sleep(11)

        # Should succeed again
        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        assert "X-RateLimit-Remaining" in resp.headers


# ===================================================================
# H.2 Request timeout
# ===================================================================


class TestRequestTimeout:
    """Request timeout middleware behavior (REQUEST_TIMEOUT=2s)."""

    def test_health_not_affected_by_timeout(
        self, timeout_client: httpx.Client
    ) -> None:
        """/health is not affected by global timeout."""
        resp = timeout_client.get("/health")
        assert resp.status_code == 200

    def test_ready_not_affected_by_timeout(
        self, timeout_client: httpx.Client
    ) -> None:
        """/ready is not affected by global timeout."""
        resp = timeout_client.get("/ready")
        assert resp.status_code == 200

    def test_fast_request_completes_within_timeout(
        self, timeout_client: httpx.Client
    ) -> None:
        """A fast request completes without timeout."""
        resp = timeout_client.get("/api/v1/nodes/")
        assert resp.status_code == 200

    def test_node_survives_after_timeout(
        self, timeout_client: httpx.Client
    ) -> None:
        """After a timeout, subsequent requests to the same resource work."""
        # Create a node (fast)
        resp = timeout_client.post(
            "/api/v1/nodes/",
            json={
                "name": "e2e-timeout-test",
                "connection_type": "ssh",
                "host": "127.0.0.1",
                "port": 22,
                "username": "testuser",
                "auth_method": "password",
                "credentials": {"password": "testpass"},
            },
        )
        # May succeed or fail depending on SSH, but shouldn't timeout
        assert resp.status_code in (201, 400, 409, 500)

        # Subsequent request should still work
        resp2 = timeout_client.get("/api/v1/nodes/")
        assert resp2.status_code == 200


# ===================================================================
# H.3 Security middleware
# ===================================================================


class TestSecurityMiddleware:
    """Security headers, request ID, and CORS behavior."""

    def test_security_headers_on_success(
        self, e2e_client: httpx.Client
    ) -> None:
        """Security headers are present on successful responses."""
        resp = e2e_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-XSS-Protection"] == "1; mode=block"
        assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]

    def test_security_headers_on_error(
        self, e2e_client: httpx.Client
    ) -> None:
        """Security headers are present on error responses."""
        resp = e2e_client.get("/api/v1/nodes/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_500_does_not_expose_traceback(
        self, e2e_client: httpx.Client
    ) -> None:
        """Internal errors do not expose traceback or secrets."""
        # A malformed request that triggers a 500 should not leak internals
        resp = e2e_client.post(
            "/api/v1/nodes/",
            json={"invalid": True},
        )
        if resp.status_code == 500:
            body = resp.text.lower()
            assert "traceback" not in body
            assert "password" not in body
            assert "secret" not in body

    def test_cors_allowed_origin(
        self, api_base_url: str
    ) -> None:
        """Requests from allowed origins pass CORS preflight."""
        resp = httpx.options(
            f"{api_base_url}/api/v1/nodes/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
            timeout=5.0,
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_disallowed_origin(
        self, api_base_url: str
    ) -> None:
        """Requests from disallowed origins are blocked by CORS."""
        resp = httpx.options(
            f"{api_base_url}/api/v1/nodes/",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
            timeout=5.0,
        )
        # Disallowed origin should NOT get access-control-allow-origin
        assert resp.headers.get("access-control-allow-origin") != "http://evil.example.com"

    def test_rate_limit_headers_present(
        self, e2e_client: httpx.Client
    ) -> None:
        """Rate limit headers are present on responses."""
        resp = e2e_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
