"""Immutable application DTOs for persistent script scheduling."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ScheduleRequestDTO:
    """Desired persistent schedule state."""

    cron: str
    node_ids: tuple[UUID, ...]
    params: tuple[tuple[str, Any], ...] = ()
    timezone: str = "UTC"
    misfire_grace_seconds: int = 60


@dataclass(frozen=True, slots=True)
class ScheduleViewDTO:
    """Application view of one persistent schedule."""

    id: UUID
    script_id: UUID
    cron: str
    timezone: str
    node_ids: tuple[UUID, ...]
    params: tuple[tuple[str, Any], ...]
    enabled: bool
    misfire_grace_seconds: int
    operational_state: str
    last_error_type: str | None = None
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    next_run_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RuntimeScheduleDTO:
    """Runtime projection passed to a scheduler adapter."""

    schedule_id: UUID
    script_id: UUID
    cron: str
    timezone: str
    node_ids: tuple[UUID, ...]
    params: tuple[tuple[str, Any], ...]
    misfire_grace_seconds: int


@dataclass(frozen=True, slots=True)
class RuntimeJobViewDTO:
    """Adapter-neutral view of one registered runtime job."""

    script_id: UUID
    next_run_at: datetime | None


@dataclass(frozen=True, slots=True)
class ScheduleReconciliationResultDTO:
    """Summary of rebuilding runtime jobs from persistent state."""

    restored: int
    failed: int
