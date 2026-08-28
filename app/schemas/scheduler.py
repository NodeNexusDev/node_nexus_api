"""Schemas for script scheduling."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import JsonObject


class ScheduleRequest(BaseModel):
    """Request to schedule a script."""

    cron: str = Field(
        min_length=5,
        max_length=60,
        description="Cron expression (e.g., '0 9 * * *')",
    )
    node_ids: list[UUID] = Field(min_length=1, description="Target node IDs")
    params: JsonObject = Field(default_factory=dict)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    misfire_grace_seconds: int = Field(default=60, ge=1, le=86400)


class ScheduleResponse(BaseModel):
    """Response for schedule operation."""

    script_id: str
    cron: str
    timezone: str = "UTC"
    message: str = "Script scheduled successfully"


class ScheduledJob(BaseModel):
    """Information about a scheduled job."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    script_id: UUID
    cron: str
    timezone: str
    node_ids: list[UUID] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)
    enabled: bool
    misfire_grace_seconds: int
    operational_state: str
    last_error_type: str | None = None
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    next_run_at: datetime | None = None
