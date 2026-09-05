"""Bulk node operation DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from app.core.types import NodeStatus


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
class BulkNodeCheckDetailDTO:
    node_id: str
    success: bool
    error: str | None = None
    new_status: NodeStatus | None = None


@dataclass(frozen=True, slots=True)
class BulkNodeCheckResultDTO:
    total: int
    succeeded: int
    failed: int
    node_ids: tuple[uuid.UUID, ...]
    details: tuple[BulkNodeCheckDetailDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class BulkValidateCredentialsResultDTO:
    node_id: uuid.UUID
    node_name: str
    status: Literal["success", "error"]
    message: str = ""
