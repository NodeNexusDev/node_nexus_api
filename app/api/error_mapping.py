"""Central mapping of domain errors to HTTP responses."""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    APIKeyExpiredError,
    APIKeyNotFoundError,
    APIKeyRevokedError,
    AuditWriteError,
    AuthenticationError,
    CommandNotFoundError,
    ConnectionFailedError,
    ContainerNotFoundError,
    CredentialDecryptionError,
    DockerDaemonError,
    DockerError,
    DockerValidationError,
    DomainError,
    ExecutionNotFoundError,
    FavoriteNotFoundError,
    HostKeyFetchError,
    ImageNotFoundError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    InvalidTokenError,
    NetworkNotFoundError,
    NodeNameConflictError,
    NodeNotFoundError,
    NoteNotFoundError,
    RequestTimeoutError,
    ScheduledScriptExecutionError,
    ScheduleNotFoundError,
    SchedulePersistenceError,
    SchedulerOwnershipError,
    ScheduleValidationError,
    ScriptNotFoundError,
    TagNotFoundError,
    TemplateRenderError,
    TokenExpiredError,
    UnsupportedConfigFormatError,
    UserAlreadyExistsError,
    UserNotFoundError,
    VolumeNotFoundError,
)

logger = structlog.get_logger()

DOMAIN_ERROR_STATUS: dict[type[DomainError], int] = {
    NodeNotFoundError: 404,
    NodeNameConflictError: 409,
    CommandNotFoundError: 404,
    ScriptNotFoundError: 404,
    APIKeyNotFoundError: 404,
    APIKeyRevokedError: 401,
    APIKeyExpiredError: 401,
    AuthenticationError: 401,
    TagNotFoundError: 404,
    ConnectionFailedError: 503,
    HostKeyFetchError: 503,
    CredentialDecryptionError: 503,
    TemplateRenderError: 422,
    ContainerNotFoundError: 404,
    NetworkNotFoundError: 404,
    VolumeNotFoundError: 404,
    ImageNotFoundError: 404,
    DockerDaemonError: 503,
    DockerValidationError: 422,
    DockerError: 502,
    RequestTimeoutError: 504,
    UnsupportedConfigFormatError: 422,
    ScheduleValidationError: 422,
    ScheduleNotFoundError: 404,
    SchedulerOwnershipError: 503,
    SchedulePersistenceError: 503,
    AuditWriteError: 503,
    ExecutionNotFoundError: 404,
    ScheduledScriptExecutionError: 422,
    FavoriteNotFoundError: 404,
    NoteNotFoundError: 404,
    InvalidCredentialsError: 401,
    UserNotFoundError: 404,
    UserAlreadyExistsError: 409,
    TokenExpiredError: 401,
    InvalidTokenError: 401,
    InsufficientPermissionsError: 403,
    DomainError: 422,
}

PUBLIC_ERROR_MESSAGES: dict[type[DomainError], str] = {
    ConnectionFailedError: "Remote connection failed",
    HostKeyFetchError: "SSH host key verification failed",
    CredentialDecryptionError: "Credential processing failed",
    ContainerNotFoundError: "Docker container not found",
    NetworkNotFoundError: "Docker network not found",
    VolumeNotFoundError: "Docker volume not found",
    ImageNotFoundError: "Docker image not found",
    DockerDaemonError: "Docker daemon unavailable",
    DockerError: "Docker operation failed",
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
    )
    message = PUBLIC_ERROR_MESSAGES.get(type(exc), str(exc))
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={
            "code": type(exc).__name__,
            "message": message,
            "request_id": request_id,
            "detail": message,
        },
    )
