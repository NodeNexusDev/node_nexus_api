"""Shared FastAPI dependencies."""

import hmac
import uuid
from dataclasses import dataclass
from typing import Literal

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.core.config import get_settings

audit = structlog.get_logger("audit")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_SCHEME = HTTPBearer(auto_error=False)


# ── Unified Principal ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Principal:
    """Unified identity across JWT and API key authentication.

    ``identifier`` is always a plain string suitable for direct storage
    (JWT user UUID or API key prefix).  ``source`` tells which mechanism was used.
    """

    source: Literal["jwt", "api_key"]
    identifier: str


# ── Dual-auth principal resolver ─────────────────────────────────────────────


@inject
async def get_current_principal(
    api_key_service: FromDishka[APIKeyAuthenticationService],
    jwt_handler: FromDishka[JWTHandler],
    bearer: HTTPAuthorizationCredentials | None = Security(BEARER_SCHEME),
    api_key: str | None = Security(API_KEY_HEADER),
) -> Principal:
    """Resolve a principal using an unambiguous, fail-closed credential order.

    Priority:
        1. ``Authorization: Bearer <token>`` → JWT
        2. ``X-API-Key`` header → API key (including master key shortcut)
        3. If neither present → 401
        4. If a Bearer token is present but invalid → 401 without API key fallback

    Returns:
        Principal with ``source == "jwt"`` or ``"api_key"``.
        For master keys the identifier is ``"master"`` and source is ``"jwt"``.
    """
    if bearer:
        user_id, claims = _decode_access_token(jwt_handler, bearer.credentials)
        settings = get_settings()
        x_api_key_claim = claims.get("x-api-key")
        if (
            settings.MASTER_API_KEY
            and isinstance(x_api_key_claim, str)
            and hmac.compare_digest(x_api_key_claim, settings.MASTER_API_KEY)
        ):
            audit.info("auth.master_key_used")
            return Principal(source="jwt", identifier="master")
        audit.info("auth.jwt_used", user_id=str(user_id))
        return Principal(source="jwt", identifier=str(user_id))

    # Fallback: X-API-Key
    if api_key:
        settings = get_settings()
        if settings.MASTER_API_KEY and hmac.compare_digest(
            api_key, settings.MASTER_API_KEY
        ):
            audit.info("auth.master_key_used")
            return Principal(source="jwt", identifier="master")

        principal = await api_key_service.authenticate(api_key)
        audit.info("auth.api_key_used", key_prefix=principal.key_prefix)
        return Principal(source="api_key", identifier=principal.key_prefix)

    raise HTTPException(status_code=401, detail="Not authenticated")


# ── Write scope resolver (dual-auth) ─────────────────────────────────────────


@inject
async def require_write_or_jwt_scope(
    api_key_service: FromDishka[APIKeyAuthenticationService],
    jwt_handler: FromDishka[JWTHandler],
    bearer: HTTPAuthorizationCredentials | None = Security(BEARER_SCHEME),
    api_key: str | None = Security(API_KEY_HEADER),
) -> Principal:
    """Require write authorization for both JWT and API key flows.

    - JWT superuser → accepted
    - JWT non-superuser → 403
    - API key with ``read-write`` → accepted
    - API key with ``read-only`` → 403
    - No auth → 401
    - Invalid JWT → 401 without API key fallback

    Returns:
        The resolved :class:`Principal`.
    """
    if bearer:
        user_id, claims = _decode_access_token(jwt_handler, bearer.credentials)
        if not claims.get("is_superuser"):
            audit.warning("auth.write_denied_jwt_user", user_id=str(user_id))
            raise HTTPException(status_code=403, detail="Superuser privileges required")
        audit.info("auth.write_allowed_superuser", user_id=str(user_id))
        return Principal(source="jwt", identifier=str(user_id))

    # Fallback: X-API-Key
    if api_key:
        settings = get_settings()
        if settings.MASTER_API_KEY and hmac.compare_digest(
            api_key, settings.MASTER_API_KEY
        ):
            audit.info("auth.master_key_used")
            return Principal(source="jwt", identifier="master")

        principal = await api_key_service.authenticate(api_key)
        if principal.scope == "read-only":
            audit.warning("auth.read_only_denied", key_prefix=principal.key_prefix)
            raise HTTPException(status_code=403, detail="API key has read-only scope")
        audit.info("auth.write_allowed_api_key", key_prefix=principal.key_prefix)
        return Principal(source="api_key", identifier=principal.key_prefix)

    raise HTTPException(status_code=401, detail="Not authenticated")


# ── Legacy helpers (kept for gradual migration) ──────────────────────────────


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
    """Validate API key from X-API-Key header (legacy)."""
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
    """Require write scope for the API key (legacy)."""
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
    jwt_handler: FromDishka[JWTHandler],
    bearer: HTTPAuthorizationCredentials | None = Security(BEARER_SCHEME),
) -> uuid.UUID:
    """Extract user ID from JWT token in Authorization header."""
    if bearer:
        user_id, _claims = _decode_access_token(jwt_handler, bearer.credentials)
        return user_id

    raise HTTPException(status_code=401, detail="Not authenticated")


@inject
async def require_superuser(
    jwt_handler: FromDishka[JWTHandler],
    bearer: HTTPAuthorizationCredentials | None = Security(BEARER_SCHEME),
) -> uuid.UUID:
    """Require JWT authentication with superuser role."""
    if bearer:
        user_id, claims = _decode_access_token(jwt_handler, bearer.credentials)
        if not claims.get("is_superuser"):
            raise HTTPException(status_code=403, detail="Superuser privileges required")
        return user_id

    raise HTTPException(status_code=401, detail="Not authenticated")
