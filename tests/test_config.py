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
        DEBUG=False,
        LOG_LEVEL="INFO",
    )
    assert settings.DEBUG is False
    assert settings.LOG_LEVEL == "INFO"


def test_domain_error_hierarchy():
    """Test that domain errors inherit from DomainError."""
    assert issubclass(NodeNotFoundError, DomainError)
    assert issubclass(ConnectionFailedError, DomainError)


def test_settings_ignores_extra_env_vars():
    """Test that extra env vars (e.g. POSTGRES_*) don't cause validation errors."""
    import os

    os.environ["POSTGRES_USER"] = "postgres"
    os.environ["POSTGRES_PASSWORD"] = "secret"
    os.environ["POSTGRES_DB"] = "node_nexus"
    try:
        settings = Settings(
            DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
            SECRET_KEY="test-secret",
        )
        assert settings.DATABASE_URL == "postgresql+asyncpg://test:test@localhost/test"
    finally:
        os.environ.pop("POSTGRES_USER", None)
        os.environ.pop("POSTGRES_PASSWORD", None)
        os.environ.pop("POSTGRES_DB", None)


def test_cors_origins_default():
    """Test that CORS_ORIGINS has a sensible default."""
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        SECRET_KEY="test-secret",
    )
    assert isinstance(settings.CORS_ORIGINS, list)
    assert len(settings.CORS_ORIGINS) > 0
