"""Unit tests for rate_limit core module."""

import pytest
from pyrate_limiter import Limiter

from app.core.rate_limit import (
    _fallback_init,
    close_rate_limiter,
    get_limiter,
)


class TestRateLimitModule:
    def test_get_limiter_returns_instance(self) -> None:
        limiter = get_limiter()
        assert isinstance(limiter, Limiter)

    def test_fallback_init(self) -> None:
        _fallback_init()
        limiter = get_limiter()
        assert isinstance(limiter, Limiter)

    @pytest.mark.asyncio
    async def test_close_rate_limiter(self) -> None:
        await close_rate_limiter()
        # Should not raise
