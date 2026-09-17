"""Central mapping of domain errors to HTTP responses."""

import re
from http import HTTPStatus

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.error_sanitize import (
    DOMAIN_ERROR_STATUS,  # noqa: F401  (re-export for HTTP-layer consumers)
    PUBLIC_ERROR_MESSAGES,
    sanitize_bulk_error,  # noqa: F401  (re-export for HTTP-layer consumers)
    status_for_domain_error,  # noqa: F401  (re-export for HTTP-layer consumers)
)
from app.core.exceptions import DomainError

logger = structlog.get_logger()

ERROR_TYPE_BASE = "https://nodenexusdev.github.io/node_nexus_api/en/errors"


def _error_slug(code: str) -> str:
    s = code.replace("_", "-")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "-", s)
    return s.lower()


def problem_content(
    *,
    status_code: int,
    code: str,
    detail: str,
    request_id: str | None,
    path: str,
) -> dict[str, object]:
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = f"HTTP {status_code}"
    return {
        "type": f"{ERROR_TYPE_BASE}/{_error_slug(code)}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "message": detail,
        "request_id": request_id,
        "instance": path,
    }


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate a domain error into the stable HTTP error contract."""
    if not isinstance(exc, DomainError):  # pragma: no cover - registered by type
        raise exc
    status_code = status_for_domain_error(exc)
    if status_code >= 500:
        logger.error(
            "http.domain_error",
            path=request.url.path,
            error_type=type(exc).__name__,
            status_code=status_code,
            detail=str(exc),
            exc_info=exc,
        )
        message = PUBLIC_ERROR_MESSAGES.get(type(exc), "Internal server error")
    else:
        logger.warning(
            "http.domain_error",
            path=request.url.path,
            error_type=type(exc).__name__,
            status_code=status_code,
        )
        message = PUBLIC_ERROR_MESSAGES.get(type(exc), str(exc))
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content=problem_content(
            status_code=status_code,
            code=type(exc).__name__,
            detail=message,
            request_id=request_id,
            path=request.url.path,
        ),
        media_type="application/problem+json",
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback 500 handler for unhandled exceptions.

    Ensures 500 Internal Server Error is always logged at error level
    and returned as stable envelope. Covers 5xx including 502/504
    documentation for gateway errors.
    """

    logger.error(
        "http.internal_error",
        path=request.url.path,
        error_type=type(exc).__name__,
        status_code=500,
        exc_info=exc,
    )
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content=problem_content(
            status_code=500,
            code="InternalError",
            detail="Internal server error",
            request_id=request_id,
            path=request.url.path,
        ),
        media_type="application/problem+json",
    )
