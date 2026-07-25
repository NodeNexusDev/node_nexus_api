"""Audit log repository implementation."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
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

    async def count_all(self) -> int:
        """Count all audit log entries."""
        result = await self._session.execute(select(func.count(AuditLogModel.id)))
        return result.scalar_one()

    async def delete_before(self, cutoff: datetime) -> int:
        """Delete audit logs older than cutoff date.

        Returns:
            Number of deleted rows.
        """
        stmt = delete(AuditLogModel).where(AuditLogModel.created_at < cutoff)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return cast(CursorResult, result).rowcount
