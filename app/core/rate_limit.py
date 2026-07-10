"""Rate limiting configuration with Redis backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pyrate_limiter import Duration, Limiter, Rate, RedisBucket

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = structlog.get_logger()

_bucket: RedisBucket | None = None
_limiter: Limiter | None = None
_redis: aioredis.Redis | None = None


async def init_rate_limiter(redis_url: str) -> None:
    """Initialize Redis-backed rate limiter."""
    global _bucket, _limiter, _redis

    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(redis_url, decode_responses=True)
        await _redis.ping()

        rate = Rate(10, Duration.MINUTE)
        _bucket = RedisBucket(
            rates=[rate],
            redis=_redis,
            bucket_key="rate-limit:ssh",
            script_hash="be8167afc95f25615961866ad639b736828f12b5",
        )
        _limiter = Limiter(_bucket)
        logger.info("rate_limiter.initialized", backend="redis")
    except Exception:
        logger.warning("rate_limiter.redis_failed", backend="in-memory")
        _fallback_init()


def _fallback_init() -> None:
    """Fallback to in-memory rate limiter."""
    global _limiter

    from pyrate_limiter import InMemoryBucket

    rate = Rate(10, Duration.MINUTE)
    bucket = InMemoryBucket(rates=[rate])
    _limiter = Limiter(bucket)


def get_limiter() -> Limiter:
    """Get the rate limiter instance."""
    global _limiter
    if _limiter is None:
        _fallback_init()
    return _limiter


async def close_rate_limiter() -> None:
    """Close Redis connection."""
    global _redis, _bucket, _limiter
    if _redis:
        await _redis.aclose()
        _redis = None
    _bucket = None
    _limiter = None
