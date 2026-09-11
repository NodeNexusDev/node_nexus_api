"""Core constants for NodeNexus API."""

from typing import Annotated

from pydantic import Field

from app.models.types import DEFAULT_TIMEOUT, TIMEOUT_MAX, TIMEOUT_MIN

__all__ = [
    "DEFAULT_TIMEOUT",
    "TIMEOUT_MAX",
    "TIMEOUT_MIN",
    "Timeout",
    "OptionalTimeout",
]

Timeout = Annotated[  # noqa: E501
    int,
    Field(
        ge=TIMEOUT_MIN,
        le=TIMEOUT_MAX,
        description="Execution timeout in seconds (1..3600)",
    ),
]

OptionalTimeout = Annotated[  # noqa: E501
    int | None,
    Field(  # noqa: E501
        default=None,
        ge=TIMEOUT_MIN,
        le=TIMEOUT_MAX,
        description="Optional timeout override (1..3600)",
    ),
]
