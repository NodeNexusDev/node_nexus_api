"""Port for exporting audit logs."""

from __future__ import annotations

from typing import Protocol

from app.application.dto.export import AuditExportQueryDTO, AuditExportRowDTO


class AuditExporter(Protocol):
    async def export_audit(
        self,
        query: AuditExportQueryDTO,
    ) -> list[AuditExportRowDTO]: ...
