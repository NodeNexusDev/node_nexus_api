"""Node status history DTOs."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NodeStatusChangeDTO:
    node_id: uuid.UUID
    old_status: str | None
    new_status: str
    source: str


@dataclass(frozen=True, slots=True)
class NodeStatusHistoryRecordDTO:
    id: uuid.UUID
    node_id: uuid.UUID | None
    old_status: str | None
    new_status: str
    source: str
    changed_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class NodeStatusHistoryQueryDTO:
    node_id: uuid.UUID
    offset: int = 0
    limit: int = 20


@dataclass(frozen=True, slots=True)
class NodeStatusHistoryPageDTO:
    items: tuple[NodeStatusHistoryRecordDTO, ...]
    total: int
