"""Audit log API endpoints."""

import uuid
from datetime import datetime

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.responses import PlainTextResponse, Response

from app.api.deps import (
    Principal,
    get_current_principal,
    require_write_or_jwt_scope,
)
from app.application.dto.audit import AuditLogDTO
from app.application.dto.export import AuditExportFormat, AuditExportQueryDTO
from app.application.export_utils import rows_to_csv, rows_to_json
from app.application.ports.export import AuditExporter
from app.application.services.audit_log_service import AuditLogService
from app.schemas.audit_log import AuditLogResponse
from app.schemas.common import PaginatedResponse

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/audit", tags=["audit"], route_class=DishkaRoute)


@router.get("/", response_model=PaginatedResponse[AuditLogResponse])
@inject
async def get_audit_logs(
    service: FromDishka[AuditLogService],
    node_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    user: str | None = Query(None, description="Filter by user"),
    date_from: datetime | None = Query(None, description="Filter from date (ISO 8601)"),
    date_to: datetime | None = Query(None, description="Filter to date (ISO 8601)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: Principal = Security(get_current_principal),
) -> PaginatedResponse[AuditLogResponse]:
    """Get audit logs with optional filters and pagination."""
    audit.info(
        "api.audit.list",
        node_id=str(node_id) if node_id else None,
        action=action,
        user=user,
        page=page,
        size=size,
    )
    result = await service.get_logs(
        node_id=node_id,
        action=action,
        user=user,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    return PaginatedResponse(
        items=[_to_response(item) for item in result.items],
        total=result.total,
        page=page,
        size=size,
    )


@router.delete("/", status_code=204)
@inject
async def delete_audit_logs(
    service: FromDishka[AuditLogService],
    confirm: str | None = Query(None),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete all audit log entries.

    Requires ?confirm=yes parameter to prevent accidental deletion.
    Only master key can delete all logs.
    """
    if _key.identifier != "master":
        raise HTTPException(
            status_code=403, detail="Only master key can delete all audit logs"
        )
    if confirm != "yes":
        raise HTTPException(
            status_code=422,
            detail="Add ?confirm=yes to confirm deletion of all audit logs",
        )
    audit.info("api.audit.delete_all")
    await service.delete_all_logs()


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


@router.get(
    "/export",
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
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    action: str | None = Query(None),
    node_id: uuid.UUID | None = Query(None),
    fmt: AuditExportFormat = Query("csv"),
    _key: Principal = Security(get_current_principal),
) -> Response:
    """Export audit logs as CSV or JSON."""
    audit.info("api.audit.export", format=fmt)
    query = AuditExportQueryDTO(
        date_from=from_date,
        date_to=to_date,
        action=action,
        node_id=node_id,
        fmt=fmt,
    )
    rows = await exporter.export_audit(query)
    if fmt == "json":
        return Response(
            content=__import__("json").dumps(rows_to_json(rows), default=str),
            media_type="application/json",
        )
    return PlainTextResponse(content=rows_to_csv(rows), media_type="text/csv")
