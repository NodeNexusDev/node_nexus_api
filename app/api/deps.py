"""Shared FastAPI dependencies."""

import hmac
import uuid

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.core.config import get_settings

audit = structlog.get_logger("audit")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _extract_bearer_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _decode_access_token(
    jwt_handler: JWTHandler, token: str
) -> tuple[uuid.UUID, dict[str, str | int | bool | float | None]]:
    """Decode access token and return (user_id, claims).

    Raises:
        HTTPException: 401 if token is invalid.
    """
    try:
        payload = jwt_handler.decode_token(token, expected_type="access")
        sub = payload["sub"]
        if not isinstance(sub, str):
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return uuid.UUID(sub), payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


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


@inject
async def get_current_user_id(
    request: Request,
    api_key_service: FromDishka[APIKeyAuthenticationService],
    jwt_handler: FromDishka[JWTHandler],
    api_key: str | None = Security(APIKeyHeader(name="X-API-Key", auto_error=False)),
) -> uuid.UUID:
    """Extract user ID from JWT token in Authorization header.

    Priority: JWT (Authorization) → API key (X-API-Key) → Master key.
    """
    token = _extract_bearer_token(request)
    if token:
        user_id, _claims = _decode_access_token(jwt_handler, token)
        return user_id

    # Try API key
    if api_key:
        settings = get_settings()
        if settings.MASTER_API_KEY and hmac.compare_digest(
            api_key, settings.MASTER_API_KEY
        ):
            raise HTTPException(
                status_code=401,
                detail="Master key cannot be used for user authentication",
            )
        await api_key_service.authenticate(api_key)
        raise HTTPException(
            status_code=401,
            detail="API key authentication not supported for this endpoint. Use JWT.",
        )

    raise HTTPException(status_code=401, detail="Not authenticated")


@inject
async def require_superuser(
    request: Request,
    api_key_service: FromDishka[APIKeyAuthenticationService],
    jwt_handler: FromDishka[JWTHandler],
    api_key: str | None = Security(APIKeyHeader(name="X-API-Key", auto_error=False)),
) -> uuid.UUID:
    """Require JWT authentication with superuser role.

    Raises:
        HTTPException: 401 if not authenticated, 403 if not superuser.
    """
    token = _extract_bearer_token(request)
    if token:
        user_id, claims = _decode_access_token(jwt_handler, token)
        if not claims.get("is_superuser"):
            raise HTTPException(status_code=403, detail="Superuser privileges required")
        return user_id

    # API key fallback: validate then reject (JWT required for superuser check)
    if api_key:
        settings = get_settings()
        if settings.MASTER_API_KEY and hmac.compare_digest(
            api_key, settings.MASTER_API_KEY
        ):
            raise HTTPException(
                status_code=401,
                detail="Master key cannot be used for user authentication",
            )
        await api_key_service.authenticate(api_key)
        raise HTTPException(
            status_code=401,
            detail="API key authentication not supported for this endpoint. Use JWT.",
        )

    raise HTTPException(status_code=401, detail="Not authenticated")
