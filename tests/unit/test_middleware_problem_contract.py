"""Contract tests for 429/504 middleware problem+json responses."""

import asyncio
from http import HTTPStatus
from typing import Any

from httpx2 import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.api.middleware import (
    RateLimitMiddleware,
    RequestIdMiddleware,
    TimeoutMiddleware,
)

PROBLEM_FIELDS = {
    "type",
    "title",
    "status",
    "detail",
    "code",
    "message",
    "request_id",
    "instance",
}


async def _fast_handler(request):  # noqa: ANN001, ANN202
    return JSONResponse({"status": "ok"})


async def _slow_handler(request):  # noqa: ANN001, ANN202
    await asyncio.sleep(10)
    return JSONResponse({"status": "ok"})


def _assert_problem_shape(body: dict[str, Any], *, status: int, path: str) -> None:
    assert PROBLEM_FIELDS.issubset(body.keys())
    assert body["status"] == status
    assert body["title"] == HTTPStatus(status).phrase
    assert body["message"] == body["detail"]
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["type"], str) and body["type"].startswith(
        "https://nodenexusdev.github.io/node_nexus_api/en/errors/"
    )
    assert body["instance"] == path
    assert "request_id" in body


class TestRateLimitProblemContract:
    async def test_429_problem_json_shape_and_headers(self) -> None:
        app = Starlette(routes=[Route("/test", _fast_handler)])
        app.add_middleware(RateLimitMiddleware, requests=1, window=60)
        app.add_middleware(RequestIdMiddleware)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            await ac.get("/test")
            resp = await ac.get("/test", headers={"X-Request-ID": "req-429"})

        assert resp.status_code == 429
        assert resp.headers["content-type"] == "application/problem+json"
        body = resp.json()
        _assert_problem_shape(body, status=429, path="/test")
        assert body["request_id"] == "req-429"
        assert resp.headers["x-request-id"] == "req-429"
        assert resp.headers["retry-after"]
        assert resp.headers["x-ratelimit-limit"] == "1"
        assert resp.headers["x-ratelimit-remaining"] == "0"

    async def test_429_propagates_generated_request_id(self) -> None:
        app = Starlette(routes=[Route("/test", _fast_handler)])
        app.add_middleware(RateLimitMiddleware, requests=1, window=60)
        app.add_middleware(RequestIdMiddleware)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            await ac.get("/test")
            resp = await ac.get("/test")

        assert resp.status_code == 429
        assert resp.headers["content-type"] == "application/problem+json"
        body = resp.json()
        _assert_problem_shape(body, status=429, path="/test")
        assert body["request_id"] == resp.headers["x-request-id"]


class TestTimeoutProblemContract:
    async def test_504_problem_json_shape_and_headers(self) -> None:
        app = Starlette(routes=[Route("/slow", _slow_handler)])
        app.add_middleware(TimeoutMiddleware, timeout=0.01)
        app.add_middleware(RequestIdMiddleware)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/slow", headers={"X-Request-ID": "req-504"})

        assert resp.status_code == 504
        assert resp.headers["content-type"] == "application/problem+json"
        body = resp.json()
        _assert_problem_shape(body, status=504, path="/slow")
        assert "timed out" in body["detail"]
        assert body["request_id"] == "req-504"
        assert resp.headers["x-request-id"] == "req-504"
