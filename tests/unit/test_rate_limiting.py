"""Unit tests for rate limiting."""

from pyrate_limiter import Limiter

from app.core.rate_limit import get_limiter


class TestSSHRateLimiter:
    def test_limiter_exists(self) -> None:
        limiter = get_limiter()
        assert limiter is not None

    def test_limiter_is_limiter_instance(self) -> None:
        limiter = get_limiter()
        assert isinstance(limiter, Limiter)


class TestRateLimitConfig:
    def test_rate_limit_enabled_default(self) -> None:
        from app.core.config import Settings

        settings = Settings(
            DATABASE_URL="sqlite://",
            SECRET_KEY="test",
        )
        assert settings.RATE_LIMIT_ENABLED is True

    def test_rate_limit_strings(self) -> None:
        from app.core.config import Settings

        settings = Settings(
            DATABASE_URL="sqlite://",
            SECRET_KEY="test",
        )
        assert settings.RATE_LIMIT_DEFAULT == "100/minute"
        assert settings.RATE_LIMIT_SSH == "10/minute"
