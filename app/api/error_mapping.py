"""Central mapping of domain errors to HTTP responses."""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    APIKeyExpiredError,
    APIKeyNotFoundError,
    APIKeyRevokedError,
    AuthenticationError,
    CommandNotFoundError,
    ConnectionFailedError,
    ContainerNotFoundError,
    DockerDaemonError,
    DockerError,
    DockerValidationError,
    DomainError,
    ImageNotFoundError,
    NodeNameConflictError,
    NodeNotFoundError,
    RequestTimeoutError,
    ScriptNotFoundError,
    TagNotFoundError,
    TemplateRenderError,
)

logger = structlog.get_logger()

DOMAIN_ERROR_STATUS: dict[type[DomainError], int] = {
    NodeNotFoundError: 404,
    NodeNameConflictError: 409,
    CommandNotFoundError: 404,
    ScriptNotFoundError: 404,
    APIKeyNotFoundError: 401,
    APIKeyRevokedError: 401,
    APIKeyExpiredError: 401,
    AuthenticationError: 401,
    TagNotFoundError: 404,
    ConnectionFailedError: 503,
    TemplateRenderError: 422,
    ContainerNotFoundError: 404,
    ImageNotFoundError: 404,
    DockerDaemonError: 503,
    DockerValidationError: 422,
    DockerError: 502,
    RequestTimeoutError: 504,
    DomainError: 422,
}


def status_for_domain_error(exc: DomainError) -> int:
    """Return the most specific HTTP status registered for an error."""
    return next(
        (
            status
            for error_type, status in DOMAIN_ERROR_STATUS.items()
            if isinstance(exc, error_type)
        ),
        422,
    )


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate a domain error into the stable HTTP error contract."""
    if not isinstance(exc, DomainError):  # pragma: no cover - registered by type
        raise exc
    status_code = status_for_domain_error(exc)
    log = logger.warning if status_code >= 500 else logger.info
    log(
        "http.domain_error",
        path=request.url.path,
        error_type=type(exc).__name__,
        status_code=status_code,
        detail=str(exc),
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})
