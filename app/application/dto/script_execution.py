"""Immutable DTOs for script execution use cases."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.dto.node_connection import NodeConnectionDTO
from app.application.types import JsonValue


@dataclass(frozen=True, slots=True)
class ResolvedScriptStepDTO:
    """One script step resolved before remote workers start."""

    label: str
    command: str
    on_failure: str
    resolution_error: str | None = None


@dataclass(frozen=True, slots=True)
class ScriptExecutionRequestDTO:
    """Application input for executing a script on multiple nodes."""

    node_ids: tuple[UUID, ...] = ()
    tags: tuple[str, ...] = ()
    params: tuple[tuple[str, JsonValue], ...] = ()


@dataclass(frozen=True, slots=True)
class ScriptExecutionTargetDTO:
    """Fully loaded target passed to one remote worker."""

    execution_id: UUID
    script_id: UUID
    node: NodeConnectionDTO
    steps: tuple[ResolvedScriptStepDTO, ...]


@dataclass(frozen=True, slots=True)
class ScriptStepResultDTO:
    """Result of one resolved script step."""

    step_index: int
    label: str
    command_fingerprint: str
    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool
    exit_code: int


@dataclass(frozen=True, slots=True)
class ScriptNodeResultDTO:
    """Result of executing a script on one node."""

    execution_id: UUID
    node_id: UUID
    node_name: str
    status: str
    steps: tuple[ScriptStepResultDTO, ...]


@dataclass(frozen=True, slots=True)
class ScriptExecutionBatchResultDTO:
    """Results for all requested execution targets."""

    script_id: UUID
    results: tuple[ScriptNodeResultDTO, ...]


@dataclass(frozen=True, slots=True)
class ScriptExecutionDTO:
    """Application view of one persisted execution."""

    id: UUID
    script_id: UUID
    node_id: UUID | None
    params: tuple[tuple[str, JsonValue], ...]
    status: str
    steps: tuple[ScriptStepResultDTO, ...]
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class ScriptExecutionQueryDTO:
    """Pagination input for one script's execution history."""

    script_id: UUID
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class ScriptExecutionPageDTO:
    """One page of execution history."""

    items: tuple[ScriptExecutionDTO, ...]
    total: int
