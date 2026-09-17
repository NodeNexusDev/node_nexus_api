"""Client-safe error messages shared across layers.

The mapping tables and :func:`sanitize_bulk_error` live in core (not api)
so both API handlers and application services can use them without
violating layer dependency rules. :mod:`app.api.error_mapping` re-exports
these names for HTTP-layer consumers.
"""

from typing import cast

import structlog

from app.core.exceptions import (
    APIKeyExpiredError,
    APIKeyNotFoundError,
    APIKeyRevokedError,
    AuditReadError,
    AuditStatsUnavailableError,
    AuditWriteError,
    AuthenticationError,
    CommandNotFoundError,
    CommitFailedError,
    ComposeProjectAlreadyExistsError,
    ComposeProjectNotFoundError,
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
    PackConflictError,
    PackNotFoundError,
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
    AuditStatsUnavailableError: 501,
    AuditReadError: 500,
    CommitFailedError: 503,
    ExecutionNotFoundError: 404,
    ScheduledScriptExecutionError: 422,
    FavoriteNotFoundError: 404,
    InvalidCredentialsError: 401,
    UserNotFoundError: 404,
    UserAlreadyExistsError: 409,
    TokenExpiredError: 401,
    InvalidTokenError: 401,
    InsufficientPermissionsError: 403,
    ComposeProjectNotFoundError: 404,
    ComposeProjectAlreadyExistsError: 409,
    PackNotFoundError: 404,
    PackConflictError: 409,
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
    """Return the most specific HTTP status registered for an error.

    Walks the MRO of the exception type to ensure the most specific
    registered mapping is used regardless of dict insertion order.
    Covers 502 Bad Gateway (DockerError) and 504 Gateway Timeout
    (RequestTimeoutError) explicitly.
    """
    for cls in type(exc).__mro__:
        if cls in DOMAIN_ERROR_STATUS:
            return DOMAIN_ERROR_STATUS[cast(type[DomainError], cls)]
    return 422  # pragma: no cover - DomainError fallback ensures unreachable


def sanitize_bulk_error(exc: Exception) -> str:
    """Return a client-safe message for a bulk per-item failure.

    Mirrors the HTTP domain-error contract without the HTTP layer: 4xx
    domain errors keep their curated message, 5xx domain errors and
    unexpected exceptions (SQLAlchemy/asyncpg internals, tracebacks)
    collapse to a generic message. The original is always logged.
    """
    if isinstance(exc, DomainError):
        if status_for_domain_error(exc) >= 500:
            logger.error(
                "bulk.domain_error",
                error_type=type(exc).__name__,
                exc_info=exc,
            )
            return PUBLIC_ERROR_MESSAGES.get(type(exc), "Internal server error")
        return PUBLIC_ERROR_MESSAGES.get(type(exc), str(exc))
    logger.error(
        "bulk.unexpected_error",
        error_type=type(exc).__name__,
        exc_info=exc,
    )
    return "Internal error"
