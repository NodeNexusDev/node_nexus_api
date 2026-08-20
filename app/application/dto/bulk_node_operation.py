"""Bulk node operation DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BulkNodeDeleteDTO:
    node_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class BulkNodeTagOperationDTO:
    node_ids: tuple[uuid.UUID, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BulkNodeOperationResultDTO:
    affected: int
    node_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class BulkNodeCheckResultDTO:
    total: int
    succeeded: int
    failed: int
    node_ids: tuple[uuid.UUID, ...]
