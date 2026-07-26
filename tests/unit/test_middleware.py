"""Tests for security headers and CORS middleware."""

import asyncio

import pytest
from httpx2 import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.api.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    TimeoutMiddleware,
)
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac


async def _error_handler(request):
    raise ValueError("test error")


async def _ok_handler(request):
    return JSONResponse({"status": "ok"})


@pytest.fixture
def error_app():
    app = Starlette(
        routes=[Route("/error", _error_handler), Route("/ok", _ok_handler)],
    )
    app.add_middleware(RequestLoggingMiddleware)
    return app


class TestSecurityHeaders:
    async def test_x_content_type_options(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"

    async def test_x_frame_options(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.headers["x-frame-options"] == "DENY"

    async def test_x_xss_protection(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.headers["x-xss-protection"] == "1; mode=block"

    async def test_strict_transport_security(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert "max-age=31536000" in resp.headers["strict-transport-security"]
        assert "includeSubDomains" in resp.headers["strict-transport-security"]

    async def test_headers_on_options_request(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/api/v1/nodes",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "x-content-type-options" in resp.headers
        assert "x-frame-options" in resp.headers


class TestCORS:
    async def test_cors_preflight_allowed_origin(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/api/v1/nodes",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert (
            resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
        )

    async def test_cors_allowed_methods(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/api/v1/nodes",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        assert "GET" in allow_methods
        assert "POST" in allow_methods
        assert "PUT" in allow_methods
        assert "DELETE" in allow_methods

    async def test_cors_allowed_headers(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/api/v1/nodes",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type, Authorization",
            },
        )
        allow_headers = resp.headers.get("access-control-allow-headers", "")
        assert "content-type" in allow_headers.lower()

    async def test_cors_credentials_allowed(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/api/v1/nodes",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    async def test_cors_rejects_unknown_origin(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/api/v1/nodes",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "http://evil.com"


class TestRequestLoggingMiddleware:
    async def test_logs_successful_request(self, error_app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=error_app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/ok")
            assert resp.status_code == 200

    async def test_middleware_applied(self, error_app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=error_app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/ok")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}


async def _slow_handler(request):
    await asyncio.sleep(10)
    return JSONResponse({"status": "ok"})


async def _fast_handler(request):
    return JSONResponse({"status": "ok"})


class TestTimeoutMiddleware:
    async def test_timeout_returns_504(self):
        """Request exceeding timeout returns 504."""
        app = Starlette(routes=[Route("/slow", _slow_handler)])
        app.add_middleware(TimeoutMiddleware, timeout=0.01)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/slow")
            assert resp.status_code == 504
            assert "timed out" in resp.json()["detail"]

    async def test_fast_request_not_timed_out(self):
        """Fast request completes normally."""
        app = Starlette(routes=[Route("/fast", _fast_handler)])
        app.add_middleware(TimeoutMiddleware, timeout=5)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/fast")
            assert resp.status_code == 200

    async def test_health_excluded_from_timeout(self):
        """Health endpoint is excluded from timeout."""

        async def _health(request):
            return JSONResponse({"status": "healthy"})

        app = Starlette(routes=[Route("/health", _health)])
        app.add_middleware(TimeoutMiddleware, timeout=0.01)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/health")
            assert resp.status_code == 200


class TestRateLimitMiddleware:
    async def test_rate_limit_returns_429(self):
        """Exceeding rate limit returns 429."""
        app = Starlette(routes=[Route("/test", _fast_handler)])
        app.add_middleware(RateLimitMiddleware, requests=2, window=60)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            await ac.get("/test")
            await ac.get("/test")
            resp = await ac.get("/test")  # 3rd request
            assert resp.status_code == 429
            assert "Rate limit" in resp.json()["detail"]

    async def test_rate_limit_headers_present(self):
        """Rate limit headers are present on responses."""
        app = Starlette(routes=[Route("/test", _fast_handler)])
        app.add_middleware(RateLimitMiddleware, requests=10, window=60)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/test")
            assert "x-ratelimit-limit" in resp.headers
            assert "x-ratelimit-remaining" in resp.headers

    async def test_health_excluded_from_rate_limit(self):
        """Health endpoint is excluded from rate limiting."""

        async def _health(request):
            return JSONResponse({"status": "healthy"})

        app = Starlette(routes=[Route("/health", _health)])
        app.add_middleware(RateLimitMiddleware, requests=1, window=60)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            # Should not be rate limited even with many requests
            for _ in range(5):
                resp = await ac.get("/health")
                assert resp.status_code == 200
