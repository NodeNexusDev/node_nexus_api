"""SQLAlchemy adapters for audit queries, retention, and outbox append."""

import json
import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.audit import (
    AuditEventDTO,
    AuditLogDTO,
    AuditLogPageDTO,
    AuditLogQueryDTO,
)
from app.models.audit_log import AuditLogModel
from app.models.audit_outbox import AuditOutboxModel


class SqlAlchemyAuditLogGateway:
    """Implement audit-log queries and cleanup with short sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list_logs(self, query: AuditLogQueryDTO) -> AuditLogPageDTO:
        async with self._sessionmaker() as session:
            filters = []
            if query.node_id is not None:
                filters.append(AuditLogModel.node_id == query.node_id)
            if query.action is not None:
                filters.append(AuditLogModel.action == query.action)
            if query.user is not None:
                filters.append(AuditLogModel.user == query.user)
            if query.date_from is not None:
                filters.append(AuditLogModel.created_at >= query.date_from)
            if query.date_to is not None:
                filters.append(AuditLogModel.created_at <= query.date_to)
            count_result = await session.execute(
                select(func.count(AuditLogModel.id)).where(*filters)
            )
            result = await session.execute(
                select(AuditLogModel)
                .where(*filters)
                .order_by(AuditLogModel.created_at.desc())
                .offset(query.offset)
                .limit(query.limit)
            )
            return AuditLogPageDTO(
                items=tuple(self._to_dto(model) for model in result.scalars()),
                total=count_result.scalar_one(),
            )

    async def delete_before(self, cutoff: datetime) -> int:
        async with self._sessionmaker.begin() as session:
            result = await session.execute(
                delete(AuditLogModel).where(AuditLogModel.created_at < cutoff)
            )
            return result.rowcount if isinstance(result, CursorResult) else 0

    @staticmethod
    def _to_dto(model: AuditLogModel) -> AuditLogDTO:
        return AuditLogDTO(
            id=model.id,
            node_id=model.node_id,
            action=model.action,
            user=model.user,
            details=model.details,
            created_at=model.created_at,
        )


class RequestAuditOutbox:
    """Append an audit event in the current request transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, event: AuditEventDTO) -> None:
        self._session.add(_outbox_model(event))
        await self._session.flush()


class RequiredAuditOutbox:
    """Commit a pre-side-effect audit event in an independent transaction."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def enqueue(self, event: AuditEventDTO) -> None:
        async with self._sessionmaker.begin() as session:
            session.add(_outbox_model(event))
            await session.flush()


def _outbox_model(event: AuditEventDTO) -> AuditOutboxModel:
    return AuditOutboxModel(
        id=uuid.uuid4(),
        payload={
            "node_id": str(event.node_id) if event.node_id else None,
            "action": event.action,
            "user": event.user,
            "details": json.dumps(event.details) if event.details else None,
        },
        status="pending",
    )
