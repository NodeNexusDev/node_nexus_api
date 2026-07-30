"""Startup retention job for immutable audit logs."""

from datetime import UTC, datetime, timedelta

from app.application.ports.audit_log import AuditLogWriter


class AuditCleanupJob:
    """Apply the configured audit-log retention policy."""

    def __init__(self, writer: AuditLogWriter, retention_days: int) -> None:
        self._writer = writer
        self._retention_days = retention_days

    async def run(self) -> int:
        """Delete expired audit logs and return the affected row count."""
        if self._retention_days <= 0:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        return await self._writer.delete_before(cutoff)
