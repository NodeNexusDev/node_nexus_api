"""Audit log query, cleanup, and outbox ports."""

from datetime import datetime
from typing import Protocol

from app.application.dto.audit import (
    AuditEventDTO,
    AuditLogPageDTO,
    AuditLogQueryDTO,
)


class AuditLogReader(Protocol):
    """Read immutable audit-log pages."""

    async def list_logs(self, query: AuditLogQueryDTO) -> AuditLogPageDTO:
        """Return one filtered audit-log page."""
        ...


class AuditLogWriter(Protocol):
    """Apply audit-log retention mutations."""

    async def delete_before(self, cutoff: datetime) -> int:
        """Delete logs older than a cutoff."""
        ...


class AuditOutboxPort(Protocol):
    """Append logical audit events to the durable outbox."""

    async def enqueue(self, event: AuditEventDTO) -> None:
        """Append one event in the adapter's transaction scope."""
        ...
