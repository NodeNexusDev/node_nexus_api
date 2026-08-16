from __future__ import annotations

import csv
import io
from typing import Protocol

from app.application.dto.export import AuditExportQueryDTO, AuditExportRowDTO


class AuditExporter(Protocol):
    async def export_audit(
        self, query: AuditExportQueryDTO,
    ) -> list[AuditExportRowDTO]: ...


def rows_to_csv(rows: list[AuditExportRowDTO]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "action", "node_id", "user", "details", "created_at"])
    for row in rows:
        writer.writerow([
            row.id, row.action, row.node_id, row.user,
            row.details, row.created_at,
        ])
    return buf.getvalue()


def rows_to_json(rows: list[AuditExportRowDTO]) -> list[dict]:
    return [
        {
            "id": r.id,
            "action": r.action,
            "node_id": r.node_id,
            "user": r.user,
            "details": r.details,
            "created_at": r.created_at,
        }
        for r in rows
    ]
