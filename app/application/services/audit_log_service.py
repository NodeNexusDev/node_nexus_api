"""Application use cases for audit-log queries and retention."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.application.dto.audit import AuditLogPageDTO, AuditLogQueryDTO
from app.application.ports.audit_log import AuditLogReader, AuditLogWriter


class AuditLogService:
    """Query and clean immutable audit logs."""

    def __init__(self, reader: AuditLogReader, writer: AuditLogWriter) -> None:
        self._reader = reader
        self._writer = writer

    async def get_logs(
        self,
        node_id: UUID | None = None,
        action: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> AuditLogPageDTO:
        return await self._reader.list_logs(
            AuditLogQueryDTO(
                node_id=node_id,
                action=action,
                offset=(page - 1) * size,
                limit=size,
            )
        )

    async def cleanup_old_logs(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        return await self._writer.delete_before(
            datetime.now(UTC) - timedelta(days=retention_days)
        )

    async def delete_all_logs(self) -> int:
        return await self._writer.delete_before(datetime.max.replace(tzinfo=UTC))
