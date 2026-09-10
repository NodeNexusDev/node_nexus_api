"""Core constants for NodeNexus API."""

from typing import Annotated

from pydantic import Field

DEFAULT_TIMEOUT: int = 30

Timeout = Annotated[int, Field(ge=1, le=3600, description="Execution timeout in seconds (1..3600)")]

OptionalTimeout = Annotated[int | None, Field(default=None, ge=1, le=3600, description="Optional timeout override (1..3600)")]
