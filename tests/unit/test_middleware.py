"""Tests for security headers and CORS middleware."""

import pytest
from httpx import ASGITransport, AsyncClient

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
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

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
