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


@router.get("/", response_model=CursorPage[AuditLogResponse])
@inject
async def list_audit_logs(
    service: FromDishka[AuditLogService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    node_id: uuid.UUID | None = Query(None, description="Filter by node ID"),
    action: str | None = Query(None, description="Filter by action"),
    user: str | None = Query(None, description="Filter by user"),
    date_from: datetime | None = Query(None, description="Filter from date (ISO 8601)"),
    date_to: datetime | None = Query(None, description="Filter to date (ISO 8601)"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[AuditLogResponse]:
    """List audit logs with cursor pagination and optional filters."""
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    audit.info(
        "api.v2.audit.list",
        cursor=cursor,
        limit=limit,
        node_id=str(node_id) if node_id else None,
        action=action,
        user=user,
    )
    result = await service.get_logs(
        node_id=node_id,
        action=action,
        user=user,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=limit,
    )
    items = [_to_response(item) for item in result.items]
    has_more = (offset + len(items)) < result.total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return CursorPage[AuditLogResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Delete all — DELETE /?confirm=yes (master only)
# ---------------------------------------------------------------------------


@router.get("/{log_id}", response_model=AuditLogResponse)
@inject
async def get_audit_log(
    log_id: uuid.UUID,
    service: FromDishka[AuditLogService],
    _principal: Principal = Security(get_current_principal),
) -> AuditLogResponse:
    """Get a single audit log entry by ID."""
    audit.info("api.v2.audit.get", log_id=str(log_id))
    try:
        raw = await cast(Any, service).get_log(log_id)
    except AttributeError as exc:
        # Fallback when get_log not exposed
        raise HTTPException(status_code=404, detail="Audit log not found") from exc
    except Exception as exc:  # noqa: BLE001
        # Map domain not found to 404, otherwise 500
        msg = str(exc).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail="Audit log not found") from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if raw is None:
        raise HTTPException(status_code=404, detail="Audit log not found")
    if isinstance(raw, AuditLogDTO):
        return _to_response(raw)
    # Generic mapping for DTO or model with from_attributes
    try:
        return AuditLogResponse.model_validate(raw, from_attributes=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Failed to map audit log") from exc
