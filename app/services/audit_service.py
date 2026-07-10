"""Audit log service for tracking operations."""

import json
from typing import Any
from uuid import UUID

import structlog

from app.repositories.audit_repo import AuditLogRepository
from app.schemas.audit_log import AuditLogResponse

logger = structlog.get_logger()


class AuditService:
    """Service for audit log operations."""

    def __init__(self, repository: AuditLogRepository):
        self._repository = repository

    async def log(
        self,
        action: str,
        node_id: UUID | None = None,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit event (fire-and-forget)."""
        try:
            await self._repository.create(
                {
                    "node_id": node_id,
                    "action": action,
                    "user": user,
                    "details": json.dumps(details) if details else None,
                }
            )
        except Exception:
            logger.warning("audit.log.failed", action=action, node_id=str(node_id))

    async def get_logs(
        self,
        node_id: UUID | None = None,
        action: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[AuditLogResponse], int]:
        """Get audit logs with pagination."""
        skip = (page - 1) * size
        logs = await self._repository.get_all(
            node_id=node_id, action=action, skip=skip, limit=size
        )
        total = await self._repository.count(node_id=node_id, action=action)
        return [AuditLogResponse.model_validate(log) for log in logs], total
