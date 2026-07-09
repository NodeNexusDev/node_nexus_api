"""Tests for core configuration."""

from app.core.config import Settings


def test_settings_default_values():
    """Test that settings have correct default values."""
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        SECRET_KEY="test-secret",
    )
    assert settings.DEBUG is False
    assert settings.LOG_LEVEL == "INFO"
