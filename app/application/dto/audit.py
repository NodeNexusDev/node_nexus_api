"""Audit event application DTO."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuditEventDTO:
    """Audit data collected by a use case before persistence."""

    action: str
    node_id: UUID | None = None
    user: str | None = None
    details: dict[str, Any] | None = None
