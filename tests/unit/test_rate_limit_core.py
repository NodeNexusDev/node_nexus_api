"""Unit tests for rate_limit core module."""

import pytest
from pyrate_limiter import Limiter

from app.core.rate_limit import (
    RateLimitState,
    close_rate_limiter,
    get_limiter,
)


class TestRateLimitModule:
    def test_get_limiter_returns_instance(self) -> None:
        limiter = get_limiter()
        assert isinstance(limiter, Limiter)

    def test_fallback_init(self) -> None:
        state = RateLimitState()
        state._fallback_init()
        assert isinstance(state.limiter, Limiter)

    @pytest.mark.asyncio
    async def test_close_rate_limiter(self) -> None:
        await close_rate_limiter()
        # Should not raise

    @pytest.mark.asyncio
    async def test_init_falls_back_on_bad_redis(self) -> None:
        state = RateLimitState()
        await state.init("redis://invalid:99999")
        assert isinstance(state.limiter, Limiter)

    def test_limiter_property_creates_on_first_access(self) -> None:
        state = RateLimitState()
        assert state._limiter is None
        _ = state.limiter
        assert state._limiter is not None

    @pytest.mark.asyncio
    async def test_close_resets_state(self) -> None:
        state = RateLimitState()
        _ = state.limiter
        assert state._limiter is not None
        await state.close()
        assert state._limiter is None
        assert state._bucket is None
