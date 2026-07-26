"""HTTP request logging, timeout, and rate limiting middleware."""

import asyncio
import time
import uuid
from collections import defaultdict

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with request_id, method, path, status, duration."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
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

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        try:
            response = await asyncio.wait_for(call_next(request), timeout=self._timeout)
            return response
        except TimeoutError:
            logger.warning(
                "http.request.timeout",
                path=request.url.path,
                timeout=self._timeout,
            )
            return Response(
                content='{"detail": "Request timed out"}',
                status_code=504,
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
            logger.warning(
                "http.request.rate_limited",
                ip=client_ip,
                path=request.url.path,
                count=current_count,
            )
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=429,
                headers={
                    "X-RateLimit-Limit": str(self._requests),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(max(1, retry_after)),
                },
                media_type="application/json",
            )

        self._ip_counts[client_ip].append(now)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
