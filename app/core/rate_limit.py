"""Rate limiting configuration with Redis/Valkey backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate, RedisBucket

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = structlog.get_logger()


class RateLimitState:
    """Encapsulates rate limiter state to avoid module-level globals."""

    def __init__(self) -> None:
        self._bucket: RedisBucket | InMemoryBucket | None = None
        self._limiter: Limiter | None = None
        self._redis: aioredis.Redis | None = None

    @property
    def limiter(self) -> Limiter:
        if self._limiter is None:
            self._fallback_init()
        assert self._limiter is not None
        return self._limiter

    def _fallback_init(self) -> None:
        rate = Rate(10, Duration.MINUTE)
        self._bucket = InMemoryBucket(rates=[rate])
        self._limiter = Limiter(self._bucket)

    async def init(self, redis_url: str) -> None:
        """Initialize Redis-backed rate limiter."""
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(redis_url, decode_responses=True)
            await self._redis.ping()

            rate = Rate(10, Duration.MINUTE)
            self._bucket = RedisBucket(
                rates=[rate],
                redis=self._redis,
                bucket_key="rate-limit:ssh",
                script_hash="be8167afc95f25615961866ad639b736828f12b5",
            )
            self._limiter = Limiter(self._bucket)
            logger.info("rate_limiter.initialized", backend="redis")
        except Exception:
            logger.warning("rate_limiter.redis_failed", backend="in-memory")
            self._fallback_init()

    async def close(self) -> None:
        """Close Redis connection and reset state."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        self._bucket = None
        self._limiter = None


_state = RateLimitState()


def get_limiter() -> Limiter:
    """Get the rate limiter instance."""
    return _state.limiter


async def init_rate_limiter(redis_url: str) -> None:
    """Initialize Redis-backed rate limiter."""
    await _state.init(redis_url)


async def close_rate_limiter() -> None:
    """Close Redis connection."""
    await _state.close()
