"""Security validation tests for application settings and user credentials."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.auth import LoginRequest, UserCreate


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "SECRET_KEY": "s" * 32,
        "ENVIRONMENT": "production",
        "ENCRYPTION_SALT": "e" * 16,
        "MASTER_API_KEY": "",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("override", "message"),
    (
        ({"SECRET_KEY": "short"}, "SECRET_KEY"),
        ({"ENCRYPTION_SALT": "short"}, "ENCRYPTION_SALT"),
        ({"MASTER_API_KEY": "short"}, "MASTER_API_KEY"),
        ({"INITIAL_SUPERUSER_PASSWORD": "short"}, "INITIAL_SUPERUSER_PASSWORD"),
    ),
)
def test_production_rejects_weak_security_configuration(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings(**override)


def test_non_production_allows_explicit_test_credentials() -> None:
    settings = _settings(
        ENVIRONMENT="test",
        SECRET_KEY="test",
        ENCRYPTION_SALT="",
        MASTER_API_KEY="test",
    )

    assert settings.ENVIRONMENT == "test"


def test_rate_limit_client_capacity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="test", RATE_LIMIT_MAX_CLIENTS=0)


def test_user_creation_requires_strong_password_but_login_remains_compatible() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="user@example.com", password="short")

    login = LoginRequest(email="user@example.com", password="short")
    assert login.password == "short"
