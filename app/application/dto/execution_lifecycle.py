"""Execution lifecycle DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryCommandDTO:
    execution_id: uuid.UUID
    node_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RetryScriptDTO:
    execution_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class CancelExecutionDTO:
    execution_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RetryCommandResultDTO:
    execution_id: str
    node_id: str | None
    command_fingerprint: str
    status: str


@dataclass(frozen=True, slots=True)
class RetryScriptResultDTO:
    execution_id: str
    status: str
