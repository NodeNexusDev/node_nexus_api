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


