"""Policies for safely persisting remote command output."""

from dataclasses import dataclass

DEFAULT_MAX_PERSISTED_OUTPUT_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class BoundedOutput:
    """Output text plus its original byte size and truncation state."""

    value: str
    original_bytes: int
    truncated: bool


def bound_output(
    value: str,
    max_bytes: int = DEFAULT_MAX_PERSISTED_OUTPUT_BYTES,
) -> BoundedOutput:
    """Limit UTF-8 output by bytes while preserving valid Unicode."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    raw = value.encode()
    if len(raw) <= max_bytes:
        return BoundedOutput(
            value=value,
            original_bytes=len(raw),
            truncated=False,
        )
    truncated = raw[:max_bytes].decode(errors="ignore")
    return BoundedOutput(
        value=truncated,
        original_bytes=len(raw),
        truncated=True,
    )
