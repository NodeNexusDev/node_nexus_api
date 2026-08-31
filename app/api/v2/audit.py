"""Audit log API v2 — cursor pagination, exports, stats and master-only cleanup."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any, Literal, cast

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security
from fastapi.responses import PlainTextResponse

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.application.dto.audit import AuditLogDTO
from app.application.dto.export import AuditExportFormat, AuditExportQueryDTO
from app.application.export_utils import rows_to_csv, rows_to_json
from app.application.ports.export import AuditExporter
from app.application.services.audit_log_service import AuditLogService
from app.schemas.audit_log import AuditLogResponse, AuditStatsBucket, AuditStatsResponse
from app.schemas.common import BulkResult, CursorPage

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/audit", tags=["audit"], route_class=DishkaRoute)


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor for pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


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
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
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
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[AuditLogResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Delete all — DELETE /?confirm=yes (master only)
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
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
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


@router.get("/stats", response_model=None)
@inject
async def get_audit_stats(
    service: FromDishka[AuditLogService],
    date_from: datetime | None = Query(None, description="Filter from date"),
    date_to: datetime | None = Query(None, description="Filter to date"),
    group_by: Literal["day", "hour", "week", "month"] | None = Query(
        None, description="Group by period"
    ),
    _principal: Principal = Security(get_current_principal),
) -> Any:  # noqa: ANN401
    """Get audit stats aggregated or bucketed.

    Without group_by returns aggregate. With group_by returns buckets.
    Delegates to AuditLogService.get_stats.
    """
    audit.info("api.v2.audit.stats", group_by=group_by)
    # Use Any cast for get_stats to keep ty happy
    try:
        raw = await cast(Any, service).get_stats(
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
        )
    except AttributeError as exc:
        # Fallback: compute total via get_logs when get_stats is not yet implemented
        raise HTTPException(
            status_code=500, detail="Audit stats not available"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        # Let domain handler map or re-raise as 422/500
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Normalize raw into typed response
    if group_by is None:
        # Aggregate path — expect total field
        if isinstance(raw, dict):
            total = int(raw.get("total", 0))
            buckets_raw = raw.get("buckets", [])
            buckets = [
                AuditStatsBucket(
                    bucket=str(b.get("bucket", b.get("period", ""))),
                    count=int(b.get("count", b.get("total", 0))),
                )
                for b in buckets_raw
                if isinstance(b, dict)
            ]
            return AuditStatsResponse(total=total, buckets=buckets)
        total = int(getattr(raw, "total", 0))
        buckets_attr = getattr(raw, "buckets", [])
        buckets: list[AuditStatsBucket] = []
        for b in buckets_attr:  # type: ignore[assignment]
            if isinstance(b, dict):
                buckets.append(
                    AuditStatsBucket(
                        bucket=str(b.get("bucket", "")), count=int(b.get("count", 0))
                    )
                )
            else:
                bucket_label = str(
                    getattr(b, "bucket", getattr(b, "period", getattr(b, "group", "")))
                )
                count_val = int(getattr(b, "count", getattr(b, "total", 0)))
                buckets.append(AuditStatsBucket(bucket=bucket_label, count=count_val))
        return AuditStatsResponse(total=total, buckets=buckets)

    # group_by present -> buckets
    if isinstance(raw, dict):
        total = int(raw.get("total", 0))
        buckets_raw = raw.get("buckets", raw.get("items", []))
        buckets = []
        for b in buckets_raw:
            if isinstance(b, dict):
                buckets.append(
                    AuditStatsBucket(
                        bucket=str(b.get("bucket", b.get("period", ""))),
                        count=int(b.get("count", b.get("total", 0))),
                    )
                )
        # BulkResult for group_by
        return BulkResult[AuditStatsBucket](
            total=total if total else len(buckets),
            succeeded=len(buckets),
            failed=0,
            results=buckets,
        )
    total = int(getattr(raw, "total", 0))
    buckets_attr = getattr(raw, "buckets", getattr(raw, "items", []))
    buckets = []
    for b in buckets_attr:  # type: ignore[assignment]
        if isinstance(b, dict):
            buckets.append(
                AuditStatsBucket(
                    bucket=str(b.get("bucket", "")), count=int(b.get("count", 0))
                )
            )
        else:
            bucket_label = str(
                getattr(b, "bucket", getattr(b, "period", getattr(b, "group", "")))
            )
            count_val = int(getattr(b, "count", getattr(b, "total", 0)))
            buckets.append(AuditStatsBucket(bucket=bucket_label, count=count_val))
    return BulkResult[AuditStatsBucket](
        total=total if total else len(buckets),
        succeeded=len(buckets),
        failed=0,
        results=buckets,
    )


# ---------------------------------------------------------------------------
# Single — GET /{id} -> get single via AuditLogService.get_log
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
