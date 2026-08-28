from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.application.dto.export import (
    AuditExportFormat,
    AuditExportQueryDTO,
    AuditExportRowDTO,
)
from app.application.ports.export import AuditExporter


class ExportService:
    def __init__(self, audit_exporter: AuditExporter) -> None:
        self._audit_exporter = audit_exporter

    async def export_audit(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        action: str | None = None,
        node_id: UUID | None = None,
        fmt: AuditExportFormat = "csv",
    ) -> list[AuditExportRowDTO]:
        return await self._audit_exporter.export_audit(
            AuditExportQueryDTO(
                date_from=date_from,
                date_to=date_to,
                action=action,
                node_id=node_id,
                fmt=fmt,
            ),
        )
