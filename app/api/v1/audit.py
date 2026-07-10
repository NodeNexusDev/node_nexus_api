"""Audit log API endpoints."""

import uuid

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from app.schemas.audit_log import AuditLogResponse
from app.schemas.node import PaginatedResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", response_model=PaginatedResponse[AuditLogResponse])
@inject
async def get_audit_logs(
    service: FromDishka[AuditService],
    node_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[AuditLogResponse]:
    """Get audit logs with optional filters and pagination."""
    logs, total = await service.get_logs(
        node_id=node_id, action=action, page=page, size=size
    )
    return PaginatedResponse(items=logs, total=total, page=page, size=size)
