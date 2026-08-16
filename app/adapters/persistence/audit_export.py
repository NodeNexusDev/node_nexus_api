from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.export import AuditExportQueryDTO, AuditExportRowDTO
from app.models.audit_log import AuditLogModel


class SqlAlchemyAuditExporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def export_audit(
        self, query: AuditExportQueryDTO,
    ) -> list[AuditExportRowDTO]:
        stmt = select(AuditLogModel)
        if query.date_from is not None:
            stmt = stmt.where(AuditLogModel.created_at >= query.date_from)
        if query.date_to is not None:
            stmt = stmt.where(AuditLogModel.created_at <= query.date_to)
        if query.action is not None:
            stmt = stmt.where(AuditLogModel.action == query.action)
        if query.node_id is not None:
            stmt = stmt.where(AuditLogModel.node_id == str(query.node_id))
        stmt = stmt.order_by(AuditLogModel.created_at.desc()).limit(10000)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            AuditExportRowDTO(
                id=str(log.id),
                action=log.action,
                node_id=log.node_id,
                user=log.user,
                details=log.details,
                created_at=str(log.created_at),
            )
            for log in rows
        ]
