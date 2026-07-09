"""Tests for core configuration and exceptions."""

from app.core.config import Settings
from app.core.exceptions import (
    ConnectionFailedError,
    DomainError,
    NodeNotFoundError,
)


def test_settings_default_values():
    """Test that settings have correct default values."""
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        SECRET_KEY="test-secret",
    )
    assert settings.DEBUG is False
    assert settings.LOG_LEVEL == "INFO"


def test_domain_error_hierarchy():
    """Test that domain errors inherit from DomainError."""
    assert issubclass(NodeNotFoundError, DomainError)
    assert issubclass(ConnectionFailedError, DomainError)
