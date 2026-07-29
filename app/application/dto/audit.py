"""Audit event application DTO."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuditEventDTO:
    """Audit data collected by a use case before persistence."""

    action: str
    node_id: UUID | None = None
    user: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AuditLogDTO:
    """Transport-neutral immutable audit-log view."""

    id: UUID
    node_id: UUID | None
    action: str
    user: str | None
    details: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditLogQueryDTO:
    """Audit-log filtering and pagination request."""

    node_id: UUID | None = None
    action: str | None = None
    offset: int = 0
    limit: int = 20


@dataclass(frozen=True, slots=True)
class AuditLogPageDTO:
    """One page of audit-log views."""

    items: tuple[AuditLogDTO, ...]
    total: int
