"""Tests for structured logging safety processors."""

from app.core.logging import REDACTED, redact_secrets


def test_redact_secrets_handles_nested_values() -> None:
    event = {
        "password": "canary-password",
        "context": {
            "api_key": "canary-key",
            "safe": "visible",
            "items": [{"authorization": "Bearer canary"}],
        },
    }

    result = redact_secrets(None, "info", event)

    assert result["password"] == REDACTED
    assert result["context"]["api_key"] == REDACTED
    assert result["context"]["safe"] == "visible"
    assert result["context"]["items"][0]["authorization"] == REDACTED


def test_redact_secrets_removes_url_credentials() -> None:
    result = redact_secrets(
        None,
        "info",
        {"connection": "postgresql+asyncpg://user:canary@db:5432/app"},
    )

    assert result["connection"] == "postgresql+asyncpg://[REDACTED]@db:5432/app"
    assert "canary" not in result["connection"]


def test_redact_secrets_removes_command_but_keeps_fingerprint() -> None:
    result = redact_secrets(
        None,
        "info",
        {
            "command": "curl -H 'Authorization: Bearer canary' example.com",
            "command_fingerprint": "safe-fingerprint",
            "command_length": 56,
        },
    )

    assert result["command"] == REDACTED
    assert result["command_fingerprint"] == "safe-fingerprint"
    assert result["command_length"] == 56
    assert "canary" not in str(result)
