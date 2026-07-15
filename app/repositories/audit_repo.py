"""Audit log repository implementation."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLogModel


class AuditLogRepository:
    """Repository for audit log operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, data: dict[str, Any]) -> AuditLogModel:
        """Create an audit log entry."""
        log = AuditLogModel(**data)
        self._session.add(log)
        await self._session.flush()
        return log

    async def get_all(
        self,
        node_id: UUID | None = None,
        action: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[AuditLogModel]:
        """Get audit logs with optional filters."""
        query = select(AuditLogModel)
        if node_id is not None:
            query = query.where(AuditLogModel.node_id == node_id)
        if action is not None:
            query = query.where(AuditLogModel.action == action)
        query = query.order_by(AuditLogModel.created_at.desc())
        query = query.offset(skip).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        node_id: UUID | None = None,
        action: str | None = None,
    ) -> int:
        """Count audit logs with optional filters."""
        query = select(func.count(AuditLogModel.id))
        if node_id is not None:
            query = query.where(AuditLogModel.node_id == node_id)
        if action is not None:
            query = query.where(AuditLogModel.action == action)
        result = await self._session.execute(query)
        return result.scalar_one()
