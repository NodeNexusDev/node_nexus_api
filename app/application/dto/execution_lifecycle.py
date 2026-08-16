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
