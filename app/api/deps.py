"""Shared FastAPI dependencies."""

import hmac

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import get_settings
from app.services.api_key_service import APIKeyService

audit = structlog.get_logger("audit")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@inject
async def get_current_api_key(
    api_key_service: FromDishka[APIKeyService],
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

    principal = await api_key_service.validate_api_key(api_key)
    return principal.key_prefix if principal is not None else api_key[:8]


@inject
async def require_write_scope(
    api_key_service: FromDishka[APIKeyService],
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

    principal = await api_key_service.validate_api_key(api_key)
    scope = (
        principal.scope
        if principal is not None
        else await api_key_service.get_api_key_scope(api_key)
    )
    key_prefix = principal.key_prefix if principal is not None else api_key[:8]
    if scope == "read-only":
        audit.warning("auth.read_only_denied", key_prefix=key_prefix)
        raise HTTPException(status_code=403, detail="API key has read-only scope")

    return key_prefix
