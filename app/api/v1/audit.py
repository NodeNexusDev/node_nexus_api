"""Audit log API endpoints."""

import uuid
from datetime import datetime

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.audit import AuditLogDTO
from app.application.services.audit_log_service import AuditLogService
from app.schemas.audit_log import AuditLogResponse
from app.schemas.node import PaginatedResponse

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
    _key: str = Security(get_current_api_key),
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


@router.delete("/")
@inject
async def delete_audit_logs(
    service: FromDishka[AuditLogService],
    confirm: str | None = Query(None),
    _key: str = Security(require_write_scope),
) -> dict[str, int]:
    """Delete all audit log entries.

    Requires ?confirm=yes parameter to prevent accidental deletion.
    Only master key can delete all logs.
    """
    if _key != "master":
        raise HTTPException(
            status_code=403, detail="Only master key can delete all audit logs"
        )
    if confirm != "yes":
        raise HTTPException(
            status_code=422,
            detail="Add ?confirm=yes to confirm deletion of all audit logs",
        )
    audit.info("api.audit.delete_all")
    deleted = await service.delete_all_logs()
    return {"deleted_count": deleted}


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
