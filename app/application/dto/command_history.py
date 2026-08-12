"""Command execution history application DTOs."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CommandHistoryCreateDTO:
    """Immutable data for persisting one command execution record."""

    node_id: UUID
    command_fingerprint: str
    exit_code: int
    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool
    command_id: UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CommandHistoryDTO:
    """Public-safe view of one command execution record."""

    id: UUID
    node_id: UUID | None
    command_id: UUID | None
    command_fingerprint: str
    exit_code: int
    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CommandHistoryQueryDTO:
    """Immutable query for one node's command execution history."""

    node_id: UUID
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class CommandHistoryPageDTO:
    """Paginated command execution history returned by persistence."""

    items: tuple[CommandHistoryDTO, ...]
    total: int
