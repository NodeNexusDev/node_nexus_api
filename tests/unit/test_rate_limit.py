"""Unit tests for rate limiting middleware."""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.api.middleware import RateLimitMiddleware


async def _endpoint(request: Request) -> JSONResponse:
    """Simple endpoint for testing."""
    return JSONResponse(content={"status": "ok"})


async def _call_next(request: Request) -> JSONResponse:
    """Mock call_next for testing."""
    return JSONResponse(content={"ok": True})


def _create_middleware(
    requests: int = 3, window: int = 60, max_clients: int = 10_000
) -> tuple[Starlette, RateLimitMiddleware]:
    """Create a Starlette app with RateLimitMiddleware."""
    app = Starlette(routes=[Route("/api/test", _endpoint)])
    middleware = RateLimitMiddleware(
        app,
        requests=requests,
        window=window,
        max_clients=max_clients,
    )
    return app, middleware


def _make_scope(
    path: str = "/api/test",
    client_ip: str = "127.0.0.1",
) -> dict:
    """Create a ASGI scope dict."""
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "server": ("test", 80),
        "client": (client_ip, 12345),
    }


async def test_rate_limit_allows_requests_under_limit() -> None:
    """Requests under the limit should succeed."""
    app, middleware = _create_middleware()
    middleware.clear()

    for _ in range(2):
        scope = _make_scope()
        request = Request(scope)
        response = await middleware.dispatch(request, _call_next)
        assert response.status_code == 200


async def test_rate_limit_returns_headers() -> None:
    """Responses should include rate limit headers."""
    app, middleware = _create_middleware()
    middleware.clear()

    scope = _make_scope()
    request = Request(scope)
    response = await middleware.dispatch(request, _call_next)
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers


async def test_rate_limit_blocks_at_limit() -> None:
    """Requests at the limit should return 429."""
    app, middleware = _create_middleware()
    middleware.clear()

    for _ in range(3):
        scope = _make_scope()
        request = Request(scope)
        response = await middleware.dispatch(request, _call_next)
        assert response.status_code == 200

    # 4th request should be blocked
    scope = _make_scope()
    request = Request(scope)
    response = await middleware.dispatch(request, _call_next)
    assert response.status_code == 429
    assert "Retry-After" in response.headers


async def test_rate_limit_health_excluded() -> None:
    """Health endpoint should be excluded from rate limiting."""
    app, middleware = _create_middleware(requests=2)
    middleware.clear()

    for _ in range(10):
        scope = _make_scope(path="/health")
        request = Request(scope)
        response = await middleware.dispatch(request, _call_next)
        assert response.status_code == 200


async def test_rate_limit_ready_excluded() -> None:
    """Ready endpoint should be excluded from rate limiting."""
    app, middleware = _create_middleware(requests=2)
    middleware.clear()

    for _ in range(5):
        scope = _make_scope(path="/ready")
        request = Request(scope)
        response = await middleware.dispatch(request, _call_next)
        assert response.status_code == 200


async def test_rate_limit_remaining_decreases() -> None:
    """Remaining count should decrease with each request."""
    app, middleware = _create_middleware()
    middleware.clear()

    scope1 = _make_scope()
    request1 = Request(scope1)
    response1 = await middleware.dispatch(request1, _call_next)
    remaining1 = int(response1.headers.get("X-RateLimit-Remaining", "100"))

    scope2 = _make_scope()
    request2 = Request(scope2)
    response2 = await middleware.dispatch(request2, _call_next)
    remaining2 = int(response2.headers.get("X-RateLimit-Remaining", "100"))

    assert remaining2 < remaining1


async def test_rate_limit_different_ips() -> None:
    """Different IPs should have separate rate limits."""
    app, middleware = _create_middleware(requests=2)
    middleware.clear()

    # Make 2 requests from IP 1
    for _ in range(2):
        scope = _make_scope(client_ip="10.0.0.1")
        request = Request(scope)
        response = await middleware.dispatch(request, _call_next)
        assert response.status_code == 200

    # IP 1 should be blocked
    scope = _make_scope(client_ip="10.0.0.1")
    request = Request(scope)
    response = await middleware.dispatch(request, _call_next)
    assert response.status_code == 429

    # IP 2 should still work
    scope = _make_scope(client_ip="10.0.0.2")
    request = Request(scope)
    response = await middleware.dispatch(request, _call_next)
    assert response.status_code == 200


async def test_rate_limit_init() -> None:
    """RateLimitMiddleware can be initialized with custom values."""
    app = Starlette()
    middleware = RateLimitMiddleware(app, requests=50, window=30)
    assert middleware._requests == 50
    assert middleware._window == 30


async def test_rate_limit_default_values() -> None:
    """RateLimitMiddleware has correct default values."""
    app = Starlette()
    middleware = RateLimitMiddleware(app)
    assert middleware._requests == 100
    assert middleware._window == 60


async def test_rate_limit_evicts_least_recent_client_at_capacity() -> None:
    _app, middleware = _create_middleware(max_clients=2)

    for client_ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        request = Request(_make_scope(client_ip=client_ip))
        response = await middleware.dispatch(request, _call_next)
        assert response.status_code == 200

    assert list(middleware._ip_counts) == ["10.0.0.2", "10.0.0.3"]
