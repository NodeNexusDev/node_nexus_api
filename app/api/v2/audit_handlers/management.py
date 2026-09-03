# ruff: noqa: F401, I001
"""Audit log API v2 — cursor pagination, exports, stats and master-only cleanup."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal, cast

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security
from fastapi.responses import PlainTextResponse

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.api.pagination import decode_offset, encode_offset
from app.application.dto.audit import AuditLogDTO
from app.application.dto.export import AuditExportFormat, AuditExportQueryDTO
from app.application.export_utils import rows_to_csv, rows_to_json
from app.application.ports.export import AuditExporter
from app.application.services.audit_log_service import AuditLogService
from app.schemas.audit_log import AuditLogResponse, AuditStatsBucket, AuditStatsResponse
from app.schemas.common import BulkResult, CursorPage

audit = structlog.get_logger("audit")

# Compatibility aliases for tests importing private helpers
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

router = APIRouter(route_class=DishkaRoute)


def _to_response(log: AuditLogDTO) -> AuditLogResponse:
    """Map an application DTO to the HTTP response schema."""
    return AuditLogResponse(
        id=log.id,
        node_id=log.node_id,
        action=log.action,
        user=log.user,
        details=log.details,
        created_at=log.created_at,
    )


# ---------------------------------------------------------------------------
# List — GET /?cursor&limit&node_id&action&user&date_from&date_to
# ---------------------------------------------------------------------------


@router.delete("/", status_code=204)
@inject
async def delete_audit_logs(
    service: FromDishka[AuditLogService],
    confirm: str | None = Query(None, description="Confirm deletion with ?confirm=yes"),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete all audit log entries.

    Requires ?confirm=yes and master key.
    """
    if _principal.identifier != "master":
        raise HTTPException(
            status_code=403, detail="Only master key can delete all audit logs"
        )
    if confirm != "yes":
        raise HTTPException(
            status_code=422,
            detail="Add ?confirm=yes to confirm deletion of all audit logs",
        )
    audit.info("api.v2.audit.delete_all")
    await service.delete_all_logs()


# ---------------------------------------------------------------------------
# Exports — GET /exports?from_date&to_date&action&node_id&fmt&cursor&limit
# ---------------------------------------------------------------------------


@router.get(
    "/exports",
    response_model=None,
    responses={
        200: {
            "description": "Audit logs exported in the requested format.",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/AuditLogResponse"},
                    },
                },
                "text/csv": {
                    "schema": {"type": "string"},
                },
            },
        },
    },
)
@inject
async def export_audit(
    exporter: FromDishka[AuditExporter],
    from_date: datetime | None = Query(
        None, alias="from_date", description="Filter from date"
    ),
    to_date: datetime | None = Query(
        None, alias="to_date", description="Filter to date"
    ),
    action: str | None = Query(None, description="Filter by action"),
    node_id: uuid.UUID | None = Query(None, description="Filter by node ID"),
    fmt: AuditExportFormat = Query("csv", description="Export format csv|json"),
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> Response:
    """Export audit logs as CSV or JSON with cursor pagination."""
    audit.info("api.v2.audit.export", format=fmt, cursor=cursor, limit=limit)
    query = AuditExportQueryDTO(
        date_from=from_date,
        date_to=to_date,
        action=action,
        node_id=node_id,
        fmt=fmt,
    )
    rows = await exporter.export_audit(query)
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    sliced = rows[offset : offset + limit]
    if fmt == "json":
        return Response(
            content=json.dumps(rows_to_json(sliced), default=str),
            media_type="application/json",
        )
    return PlainTextResponse(content=rows_to_csv(sliced), media_type="text/csv")


# ---------------------------------------------------------------------------
# Stats — GET /stats?date_from&date_to&group_by=day|hour|week|month
# ---------------------------------------------------------------------------


