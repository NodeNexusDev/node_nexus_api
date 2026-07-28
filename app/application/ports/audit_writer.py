"""Audit persistence port."""

from typing import Protocol

from app.application.dto.audit import AuditEventDTO


class AuditWriter(Protocol):
    """Persist audit events outside concurrent remote workers."""

    async def write_events(self, events: list[AuditEventDTO]) -> None:
        """Persist a batch of audit events."""
        ...
