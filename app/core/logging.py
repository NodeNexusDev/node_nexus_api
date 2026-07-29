"""Structured logging configuration."""

import logging
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

_SENSITIVE_KEY_PARTS = (
    "password",
    "token",
    "api_key",
    "secret",
    "ssh_key",
    "authorization",
    "database_url",
)
_CREDENTIAL_URL_RE = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s]+@")
REDACTED = "[REDACTED]"


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(key) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        return _CREDENTIAL_URL_RE.sub(r"\g<scheme>[REDACTED]@", value)
    return value


def redact_secrets(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact secrets from structured event fields and nested containers."""
    return {
        key: REDACTED if _is_sensitive_key(key) else _redact_value(value)
        for key, value in event_dict.items()
    }


def configure_logging(log_level: str = "INFO", debug: bool = False) -> None:
    """Configure structlog with processors and log level."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_secrets,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer()
            if debug
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
