"""Tests for the persisted remote-output policy."""

import pytest

from app.application.policies.output import bound_output


def test_short_output_is_preserved() -> None:
    result = bound_output("hello", max_bytes=5)
    assert result.value == "hello"
    assert result.original_bytes == 5
    assert result.truncated is False


def test_output_is_bounded_by_encoded_bytes() -> None:
    result = bound_output("абв", max_bytes=5)
    assert result.value == "аб"
    assert result.original_bytes == 6
    assert result.truncated is True
    assert len(result.value.encode()) <= 5


def test_zero_limit_returns_empty_truncated_output() -> None:
    result = bound_output("data", max_bytes=0)
    assert result.value == ""
    assert result.original_bytes == 4
    assert result.truncated is True


def test_negative_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        bound_output("data", max_bytes=-1)
