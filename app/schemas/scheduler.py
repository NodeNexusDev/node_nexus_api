"""Schemas for script scheduling."""

from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleRequest(BaseModel):
    """Request to schedule a script."""

    cron: str = Field(
        min_length=5,
        max_length=60,
        description="Cron expression (e.g., '0 9 * * *')",
    )
    node_ids: list[UUID] = Field(min_length=1, description="Target node IDs")


class ScheduleResponse(BaseModel):
    """Response for schedule operation."""

    script_id: str
    cron: str
    message: str = "Script scheduled successfully"


class ScheduledJob(BaseModel):
    """Information about a scheduled job."""

    script_id: str
    cron: str
    next_run_time: str | None = None
    node_ids: list[str] = Field(default_factory=list)
