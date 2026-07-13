"""Unit tests for rate_limit core module."""

import pytest
from pyrate_limiter import Duration, Limiter, Rate

from app.core.rate_limit import (
    RateLimitState,
    close_rate_limiter,
    get_limiter,
    parse_rate,
)


class TestParseRate:
    def test_parse_minute(self) -> None:
        rate = parse_rate("10/minute")
        assert rate.limit == 10
        assert rate.interval == Duration.MINUTE

    def test_parse_second(self) -> None:
        rate = parse_rate("5/second")
        assert rate.limit == 5
        assert rate.interval == Duration.SECOND

    def test_parse_hour(self) -> None:
        rate = parse_rate("100/hour")
        assert rate.limit == 100
        assert rate.interval == Duration.HOUR

    def test_parse_day(self) -> None:
        rate = parse_rate("1000/day")
        assert rate.limit == 1000
        assert rate.interval == Duration.DAY

    def test_parse_with_trailing_s(self) -> None:
        rate = parse_rate("10/minutes")
        assert rate.limit == 10
        assert rate.interval == Duration.MINUTE

    def test_parse_invalid_unit(self) -> None:
        with pytest.raises(ValueError, match="Unknown duration unit"):
            parse_rate("10/week")


class TestRateLimitModule:
    def test_get_limiter_returns_instance(self) -> None:
        limiter = get_limiter()
        assert isinstance(limiter, Limiter)

    def test_fallback_init(self) -> None:
        state = RateLimitState()
        state._fallback_init()
        assert isinstance(state.limiter, Limiter)

    def test_fallback_init_custom_rate(self) -> None:
        state = RateLimitState()
        state._fallback_init(Rate(5, Duration.SECOND))
        assert isinstance(state.limiter, Limiter)

    @pytest.mark.asyncio
    async def test_close_rate_limiter(self) -> None:
        await close_rate_limiter()
        # Should not raise

    @pytest.mark.asyncio
    async def test_init_falls_back_on_bad_redis(self) -> None:
        state = RateLimitState()
        await state.init("redis://invalid:99999", Rate(10, Duration.MINUTE))
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
