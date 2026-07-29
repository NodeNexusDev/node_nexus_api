"""Persistent and runtime scheduler ports."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.dto.schedule import (
    RuntimeJobViewDTO,
    RuntimeScheduleDTO,
    ScheduleRequestDTO,
    ScheduleViewDTO,
)


class ScheduleReader(Protocol):
    """Read immutable persistent schedule views."""

    async def get_schedule(self, script_id: UUID) -> ScheduleViewDTO | None:
        """Return the schedule for one script."""
        ...

    async def list_enabled_schedules(self) -> list[ScheduleViewDTO]:
        """Return schedules that should have a runtime projection."""
        ...


class ScheduleWriter(Protocol):
    """Persist desired schedule state and short operational updates."""

    async def upsert_schedule(
        self, script_id: UUID, data: ScheduleRequestDTO
    ) -> ScheduleViewDTO:
        """Create or replace the desired schedule state."""
        ...

    async def delete_schedule(self, script_id: UUID) -> bool:
        """Delete a desired schedule and report whether it existed."""
        ...

    async def mark_registration(
        self,
        script_id: UUID,
        *,
        state: str,
        error_type: str | None,
        next_run_at: datetime | None = None,
    ) -> None:
        """Record the outcome of applying desired state to runtime."""
        ...

    async def mark_started(self, script_id: UUID, occurred_at: datetime) -> None:
        """Record the beginning of one scheduled execution."""
        ...

    async def mark_succeeded(self, script_id: UUID, occurred_at: datetime) -> None:
        """Record a successful scheduled execution."""
        ...

    async def mark_failed(
        self, script_id: UUID, occurred_at: datetime, error_type: str
    ) -> None:
        """Record a failed scheduled execution."""
        ...


class JobSchedulerPort(Protocol):
    """Apply and inspect ephemeral runtime jobs."""

    def is_ready(self) -> bool:
        """Return whether initial persistent reconciliation succeeded."""
        ...

    def owns_execution(self) -> bool:
        """Return whether this replica currently owns scheduled execution."""
        ...

    def validate(self, cron: str, timezone: str) -> None:
        """Validate adapter-specific trigger syntax without mutating runtime."""
        ...

    def add_or_replace(self, schedule: RuntimeScheduleDTO) -> RuntimeJobViewDTO:
        """Register a runtime job for the desired schedule."""
        ...

    def remove(self, script_id: UUID) -> bool:
        """Remove a runtime job and report whether it existed."""
        ...

    def inspect(self) -> list[RuntimeJobViewDTO]:
        """Return adapter-neutral runtime job state."""
        ...
