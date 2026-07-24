"""Audit log API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key
from app.schemas.audit_log import AuditLogResponse
from app.schemas.node import PaginatedResponse
from app.services.audit_service import AuditService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/audit", tags=["audit"], route_class=DishkaRoute)


@router.get("/", response_model=PaginatedResponse[AuditLogResponse])
@inject
async def get_audit_logs(
    service: FromDishka[AuditService],
    node_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[AuditLogResponse]:
    """Get audit logs with optional filters and pagination."""
    audit.info(
        "api.audit.list",
        node_id=str(node_id) if node_id else None,
        action=action,
        page=page,
        size=size,
    )
    logs, total = await service.get_logs(
        node_id=node_id, action=action, page=page, size=size
    )
    return PaginatedResponse(items=logs, total=total, page=page, size=size)
