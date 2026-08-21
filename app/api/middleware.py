"""HTTP request id, logging, timeout, and rate limiting middleware."""

import asyncio
import json
import time
import uuid
from collections import defaultdict
from typing import override

import structlog
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign or propagate a request id and expose it on the response."""

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class ApiVersionMiddleware(BaseHTTPMiddleware):
    """Enforce header-based API versioning via ``X-API-Version``."""

    EXCLUDED_PATHS = frozenset({"/health", "/ready", "/metrics"})

    def __init__(
        self,
        app,  # noqa: ANN001
        supported_versions: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._supported_versions = set(supported_versions or ["1"])

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        version = request.headers.get("X-API-Version", "1")
        if version not in self._supported_versions:
            return Response(
                content=json.dumps({"detail": f"Unsupported API version: {version}"}),
                status_code=400,
                headers={"X-API-Version": "1"},
                media_type="application/json",
            )

        response = await call_next(request)
        response.headers["X-API-Version"] = version
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with request_id, method, path, status, duration."""

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        client_ip = request.client.host if request.client else "unknown"

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
        )

        logger.info(
            "http.request.start",
            query=str(request.query_params) if request.query_params else None,
        )

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.exception("http.request.error", duration_ms=duration_ms)
            raise
        else:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.info(
                "http.request.complete",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces a global request timeout."""

    EXCLUDED_PATHS = frozenset({"/health", "/ready", "/metrics"})

    def __init__(self, app, timeout: int = 300) -> None:  # noqa: ANN001
        super().__init__(app)
        self._timeout = timeout

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        try:
            response = await asyncio.wait_for(call_next(request), timeout=self._timeout)
            return response
        except TimeoutError:
            request_id = getattr(request.state, "request_id", None) or ""
            logger.warning(
                "http.request.timeout",
                path=request.url.path,
                timeout=self._timeout,
            )
            return Response(
                content=json.dumps(
                    {"detail": "Request timed out", "request_id": request_id}
                ),
                status_code=504,
                headers={"X-Request-ID": request_id} if request_id else {},
                media_type="application/json",
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces per-IP rate limiting."""

    EXCLUDED_PATHS = frozenset({"/health", "/ready", "/metrics"})

    def __init__(
        self,
        app,
        requests: int = 100,
        window: int = 60,  # noqa: ANN001
    ) -> None:
        super().__init__(app)
        self._requests = requests
        self._window = window
        # TODO: consider Redis-backed rate limiting for multi-replica deployments
        self._ip_counts: dict[str, list[float]] = defaultdict(list)

    def clear(self) -> None:
        """Clear all rate limit state (for testing)."""
        self._ip_counts.clear()

    def _cleanup_old_entries(self, ip: str, now: float) -> None:
        """Remove timestamps older than the window."""
        cutoff = now - self._window
        self._ip_counts[ip] = [ts for ts in self._ip_counts[ip] if ts > cutoff]

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        self._cleanup_old_entries(client_ip, now)
        current_count = len(self._ip_counts[client_ip])

        remaining = max(0, self._requests - current_count - 1)

        if current_count >= self._requests:
            retry_after = int(self._window - (now - self._ip_counts[client_ip][0]))
            request_id = getattr(request.state, "request_id", None) or ""
            logger.warning(
                "http.request.rate_limited",
                ip=client_ip,
                path=request.url.path,
                count=current_count,
            )
            headers = {
                "X-RateLimit-Limit": str(self._requests),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(max(1, retry_after)),
            }
            if request_id:
                headers["X-Request-ID"] = request_id
            return Response(
                content=json.dumps(
                    {"detail": "Rate limit exceeded", "request_id": request_id}
                ),
                status_code=429,
                headers=headers,
                media_type="application/json",
            )

        self._ip_counts[client_ip].append(now)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


class CommitOnResponseMiddleware:
    """Commit the request-scoped DB transaction before sending HTTP headers.

    This middleware wraps the outgoing ASGI ``send`` callable and commits the
    request transaction when the application emits ``http.response.start``.
    Committing before the response leaves the server guarantees that clients
    cannot observe stale state after a successful write.

    The middleware is infrastructure: it does not contain endpoint logic and
    only orchestrates the request transaction boundary provided by Dishka.
    """

    EXCLUDED_PATHS = frozenset({"/health", "/ready", "/metrics"})

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        committed = False

        async def send_with_commit(message: Message) -> None:
            nonlocal committed

            if not committed and message.get("type") == "http.response.start":
                request = Request(scope, receive=receive, send=send)
                container = request.state.dishka_container
                session = await container.get(AsyncSession)

                if session.new or session.dirty or session.deleted:
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise

                committed = True

            await send(message)

        await self.app(scope, receive, send_with_commit)
