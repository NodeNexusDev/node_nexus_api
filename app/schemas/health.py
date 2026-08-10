"""Health check response schemas."""

from pydantic import BaseModel, Field


class ReadyCheck(BaseModel):
    """Status and detail for a single readiness check."""

    status: str
    detail: str


class ReadyResponse(BaseModel):
    """Response body for the readiness probe.

    The top-level ``status`` field is preserved for backward compatibility,
    while ``checks`` is now a nested object with ``status`` and ``detail``.
    """

    status: str
    checks: dict[str, ReadyCheck] = Field(default_factory=dict)
