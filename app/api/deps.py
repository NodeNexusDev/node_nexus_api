"""Shared FastAPI dependencies."""

import hashlib
import hmac

import structlog
from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.api_key import APIKeyModel

audit = structlog.get_logger("audit")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_api_key(
    request: Request,
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

    # Get sessionmaker from app state (set up by dishka)
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        async with session.begin():
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            result = await session.execute(
                select(APIKeyModel).where(APIKeyModel.key_hash == key_hash)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise HTTPException(status_code=401, detail="Invalid API key")
            if not model.is_active:
                raise HTTPException(status_code=401, detail="API key has been revoked")
            from datetime import UTC, datetime

            model.last_used_at = datetime.now(UTC)
            await session.flush()
            return api_key[:12]
