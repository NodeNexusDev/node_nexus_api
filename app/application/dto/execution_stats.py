from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict


class ExecutionStatsRow(TypedDict):
    """Validated aggregate row returned by an execution statistics store."""

    total: int
    successful: int
    failed: int
    cancelled: int
    avg_duration_ms: float | None
    min_duration_ms: float | None
    max_duration_ms: float | None
    last_executed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExecutionStatsDTO:
    total: int
    successful: int
    failed: int
    cancelled: int  # 0 for commands (no cancelled), tracked for scripts
    success_rate: float
    avg_duration_ms: float | None
    min_duration_ms: float | None
    max_duration_ms: float | None
    last_executed_at: datetime | None


@dataclass(frozen=True, slots=True)
class CommandStatsQueryDTO:
    command_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class ScriptStatsQueryDTO:
    script_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
