"""Tests for sanitize_bulk_error (no internals leak in bulk results)."""

from app.core.error_sanitize import sanitize_bulk_error
from app.core.exceptions import (
    ConnectionFailedError,
    DomainError,
    NodeNotFoundError,
)


def test_unexpected_exception_collapses_to_generic() -> None:
    assert sanitize_bulk_error(ValueError("secret")) == "Internal error"
    assert (
        sanitize_bulk_error(RuntimeError("(sqlalchemy...) asyncpg boo"))
        == "Internal error"
    )


def test_4xx_domain_error_keeps_message() -> None:
    assert sanitize_bulk_error(NodeNotFoundError("node 123")) == "node 123"
    assert sanitize_bulk_error(DomainError("custom 4xx")) == "custom 4xx"


def test_5xx_domain_error_uses_public_message() -> None:
    assert (
        sanitize_bulk_error(ConnectionFailedError("dial tcp: refused"))
        == "Remote connection failed"
    )


def test_no_leak_markers_in_output() -> None:
    out = sanitize_bulk_error(Exception("Traceback sqlalchemy asyncpg File "))
    for marker in ("Traceback", "sqlalchemy", "asyncpg", "File "):
        assert marker not in out
