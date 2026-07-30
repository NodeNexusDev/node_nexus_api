"""Shared FastAPI dependencies."""

import hmac

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.core.config import get_settings

audit = structlog.get_logger("audit")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@inject
async def get_current_api_key(
    api_key_service: FromDishka[APIKeyAuthenticationService],
    api_key: str | None = Security(API_KEY_HEADER),
) -> str:
    """Validate API key from X-API-Key header.

    Returns:
        "master" for master key, or the key prefix for DB keys.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    settings = get_settings()
    if settings.MASTER_API_KEY and hmac.compare_digest(
        api_key, settings.MASTER_API_KEY
    ):
        audit.info("auth.master_key_used")
        return "master"

    principal = await api_key_service.authenticate(api_key)
    return principal.key_prefix


@inject
async def require_write_scope(
    api_key_service: FromDishka[APIKeyAuthenticationService],
    api_key: str | None = Security(API_KEY_HEADER),
) -> str:
    """Require write scope for the API key.

    Master key always has read-write scope.
    DB keys must have "read-write" scope to access write endpoints.

    Returns:
        The API key prefix.

    Raises:
        HTTPException: 401 if key is missing/invalid, 403 if read-only.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    settings = get_settings()
    if settings.MASTER_API_KEY and hmac.compare_digest(
        api_key, settings.MASTER_API_KEY
    ):
        audit.info("auth.master_key_used")
        return "master"

    principal = await api_key_service.authenticate(api_key)
    if principal.scope == "read-only":
        audit.warning("auth.read_only_denied", key_prefix=principal.key_prefix)
        raise HTTPException(status_code=403, detail="API key has read-only scope")

    return principal.key_prefix
