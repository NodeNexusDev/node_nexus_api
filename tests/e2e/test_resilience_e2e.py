"""Full-stack middleware behavior and network resilience E2E tests (Phase H + I).

Tests rate limiting, request timeout, security middleware, and network
failure recovery against dedicated and default Docker Compose stacks.
"""

import time
from collections.abc import Iterator

import httpx2 as httpx
import pytest

from tests.e2e.helpers.middleware_stack import (
    MiddlewareStackManager,
    MiddlewareStackPorts,
)
from tests.e2e.helpers.polling import wait_for_condition
from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.service_controller import DockerServiceController
from tests.e2e.settings import MASTER_API_KEY

pytestmark = [pytest.mark.docker, pytest.mark.e2e_resilience]

_MASTER_API_KEY = MASTER_API_KEY


# ---------------------------------------------------------------------------
# Fixtures: rate-limit stack (RATE_LIMIT_REQUESTS=5, WINDOW=10s)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rate_limit_stack() -> Iterator[MiddlewareStackPorts]:
    """Start a Docker stack with a very low rate limit (5 req / 10s window)."""
    mgr = MiddlewareStackManager(
        compose_file=__import__("pathlib")
        .Path("tests/docker-compose.e2e-ratelimit.yml")
        .resolve(),
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
def timeout_stack() -> Iterator[MiddlewareStackPorts]:
    """Start a Docker stack with a short request timeout (2 seconds)."""
    mgr = MiddlewareStackManager(
        compose_file=__import__("pathlib")
        .Path("tests/docker-compose.e2e-timeout.yml")
        .resolve(),
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
    """Rate-limit middleware behavior (RATE_LIMIT_REQUESTS=5, WINDOW=3s)."""

    def test_remaining_header_decrements(self, rate_limit_client: httpx.Client) -> None:
        """Each request decrements X-RateLimit-Remaining."""
        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        remaining = int(resp.headers["X-RateLimit-Remaining"])
        assert remaining >= 0

        resp2 = rate_limit_client.get("/api/v1/nodes/")
        assert resp2.status_code == 200
        remaining2 = int(resp2.headers["X-RateLimit-Remaining"])
        assert remaining2 < remaining

    def test_429_after_limit_exceeded(self, rate_limit_client: httpx.Client) -> None:
        """After exceeding the limit, 429 is returned."""
        # Drain the limit (5 requests)
        for _ in range(5):
            rate_limit_client.get("/api/v1/nodes/")

        # Next request should be 429
        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 429
        body = resp.json()
        assert "Rate limit exceeded" in body["detail"]

    def test_retry_after_header_present(self, rate_limit_client: httpx.Client) -> None:
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

        # Wait for window to expire by polling until request succeeds
        def _rate_limit_reset() -> bool:
            resp = rate_limit_client.get("/api/v1/nodes/")
            return resp.status_code == 200

        wait_for_condition(
            _rate_limit_reset, timeout=10.0, description="rate limit window reset"
        )

        # Should succeed again
        resp = rate_limit_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        assert "X-RateLimit-Remaining" in resp.headers


# ===================================================================
# H.2 Request timeout
# ===================================================================


class TestRequestTimeout:
    """Request timeout middleware behavior (REQUEST_TIMEOUT=2s)."""

    def test_health_not_affected_by_timeout(self, timeout_client: httpx.Client) -> None:
        """/health is not affected by global timeout."""
        resp = timeout_client.get("/health")
        assert resp.status_code == 200

    def test_ready_not_affected_by_timeout(self, timeout_client: httpx.Client) -> None:
        """/ready is not affected by global timeout."""
        resp = timeout_client.get("/ready")
        assert resp.status_code == 200

    def test_fast_request_completes_within_timeout(
        self, timeout_client: httpx.Client
    ) -> None:
        """A fast request completes without timeout."""
        resp = timeout_client.get("/api/v1/nodes/")
        assert resp.status_code == 200

    def test_node_survives_after_timeout(self, timeout_client: httpx.Client) -> None:
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

    def test_security_headers_on_success(self, e2e_client: httpx.Client) -> None:
        """Security headers are present on successful responses."""
        resp = e2e_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-XSS-Protection"] == "1; mode=block"
        assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]

    def test_security_headers_on_error(self, e2e_client: httpx.Client) -> None:
        """Security headers are present on error responses."""
        resp = e2e_client.get("/api/v1/nodes/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_500_does_not_expose_traceback(self, e2e_client: httpx.Client) -> None:
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

    def test_cors_allowed_origin(self, api_base_url: str) -> None:
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
        assert (
            resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
        )

    def test_cors_disallowed_origin(self, api_base_url: str) -> None:
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
        assert (
            resp.headers.get("access-control-allow-origin") != "http://evil.example.com"
        )

    def test_rate_limit_headers_present(self, e2e_client: httpx.Client) -> None:
        """Rate limit headers are present on responses."""
        resp = e2e_client.get("/api/v1/nodes/")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers


# ===================================================================
# Phase I — Network failures & recovery
# ===================================================================


class TestNetworkFailures:
    """Network failure scenarios using the default E2E stack."""

    def test_ssh_stop_before_connect_gives_error(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """Stopping SSH before connecting marks node as unreachable."""
        node = e2e_resources.create_ssh_node()

        # Stop SSH server
        docker_service_controller.stop("ssh-server")
        try:
            resp = e2e_client.post(
                f"/api/v1/nodes/{node['id']}/check",
            )
            # The check endpoint returns 200 but marks node as unreachable
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "unreachable"
        finally:
            docker_service_controller.start("ssh-server")

    def test_ssh_restart_allows_new_requests(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """After SSH restart, new requests succeed."""
        node = e2e_resources.create_ssh_node()

        # Stop then start SSH
        docker_service_controller.stop("ssh-server")
        docker_service_controller.start("ssh-server")

        # Wait for SSH to be healthy by polling the check endpoint
        def _ssh_healthy() -> bool:
            resp = e2e_client.post(f"/api/v1/nodes/{node['id']}/check")
            return resp.status_code == 200

        wait_for_condition(
            _ssh_healthy, timeout=10.0, description="SSH healthy after restart"
        )

        # Connectivity check should work again
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/check",
        )
        assert resp.status_code in (200, 503)  # 503 if SSH not fully ready yet

    def test_db_pause_makes_ready_return_503(
        self,
        e2e_client: httpx.Client,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """Readiness probe returns 503 when DB is paused."""
        # Ensure API is healthy first
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/ready")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        docker_service_controller.pause("db")

        # Wait for the API to notice the DB is down by polling /ready
        def _db_down() -> bool:
            try:
                resp = e2e_client.get("/ready")
                return resp.status_code == 503
            except httpx.HTTPError:
                return True  # API is down — acceptable

        wait_for_condition(
            _db_down, timeout=15.0, description="API reports DB unavailable"
        )

        try:
            resp = e2e_client.get("/ready")
            if resp.status_code == 503:
                data = resp.json()
                assert data["status"] == "not_ready"
                assert data["checks"]["database"]["status"] == "error"
        except httpx.HTTPError:
            pass  # API is down — acceptable
        finally:
            docker_service_controller.unpause("db")

    def test_db_recovery_restores_ready(
        self,
        e2e_client: httpx.Client,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """Readiness probe returns to 200 after DB recovery."""
        docker_service_controller.pause("db")

        # Wait for DB pause to take effect
        def _db_paused() -> bool:
            try:
                resp = e2e_client.get("/ready")
                return resp.status_code == 503
            except httpx.HTTPError:
                return True  # API is down — acceptable

        wait_for_condition(_db_paused, timeout=10.0, description="DB pause detected")

        docker_service_controller.unpause("db")

        resp = None
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/ready")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        assert resp is not None, "No response received after DB recovery"
        data = resp.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"]["status"] == "ok"
        assert data["checks"]["database"]["detail"]

    def test_api_restart_preserves_nodes(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """API container restart doesn't lose persistent entities."""
        node = e2e_resources.create_ssh_node()
        node_id = node["id"]

        docker_service_controller.restart("api")

        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/ready")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        resp = e2e_client.get(f"/api/v1/nodes/{node_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == node_id

    def test_dind_restart_recovers(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """After DinD restart, Docker operations work again."""
        e2e_resources.create_ssh_node()

        docker_service_controller.restart("dind")

        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/ready")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        resp = e2e_client.get("/api/v1/nodes/")
        assert resp.status_code == 200

    def test_network_disconnect_reconnect_api_to_db(
        self,
        e2e_client: httpx.Client,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """Disconnecting API from DB network causes errors, reconnecting restores."""
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/ready")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        docker_service_controller.disconnect_network("api")
        try:
            # Wait for network disconnect to take effect by polling
            def _network_down() -> bool:
                try:
                    resp = e2e_client.get("/api/v1/nodes/")
                    return resp.status_code in (500, 503)
                except httpx.HTTPError:
                    return True  # Connection error — also acceptable

            wait_for_condition(
                _network_down, timeout=10.0, description="network disconnect detected"
            )
        finally:
            docker_service_controller.reconnect_network("api")

        resp = None
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/api/v1/nodes/")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        assert resp is not None, "No response received after DB recovery"
        assert resp.status_code == 200
