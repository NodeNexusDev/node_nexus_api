"""Remote command execution application DTO."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CommandRequestDTO:
    """Transport-independent command execution input."""

    command: str
    timeout: int | None = None


@dataclass(frozen=True, slots=True)
class CommandResultDTO:
    """Transport-independent result of a single-node command."""

    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True, slots=True)
class BulkCommandRequestDTO:
    """Transport-independent bulk command selection."""

    command: str
    node_ids: tuple[UUID, ...] = ()
    tags: tuple[str, ...] = ()
    command_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class BulkCommandResultDTO:
    """Aggregate result of a bulk command."""

    command: str
    results: tuple[CommandExecutionDTO, ...]
    total: int
    succeeded: int
    failed: int


@dataclass(frozen=True, slots=True)
class CommandExecutionDTO:
    """Transport-independent result of a command executed on one node."""

    node_id: UUID
    node_name: str
    stdout: str
    stderr: str
    exit_code: int
