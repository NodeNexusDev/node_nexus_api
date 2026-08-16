"""SQLAlchemy adapter for the dashboard reader port."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.audit import SqlAlchemyAuditLogGateway
from app.application.dto.dashboard import (
    DashboardDockerStatsDTO,
    DashboardDTO,
    DashboardEntityStatsDTO,
    DashboardNodeStatsDTO,
    DashboardRecentActivityDTO,
)
from app.models.command import CommandModel
from app.models.node import NodeModel
from app.models.script import ScriptModel


class SqlAlchemyDashboardGateway:
    """Aggregate dashboard statistics from existing tables."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._audit_gateway = SqlAlchemyAuditLogGateway(sessionmaker)

    async def get_dashboard(self) -> DashboardDTO:
        async with self._sessionmaker() as session:
            nodes = await self._count_nodes(session)
            docker = self._count_docker()
            scripts = await self._count_scripts(session)
            commands = await self._count_commands(session)
            recent = await self._recent_activity()

        return DashboardDTO(
            nodes=nodes,
            docker=docker,
            scripts=scripts,
            commands=commands,
            recent_activity=recent,
        )

    async def _count_nodes(self, session: AsyncSession) -> DashboardNodeStatsDTO:
        total = await self._scalar(session, select(func.count(NodeModel.id)))
        active = await self._scalar(
            session,
            select(func.count(NodeModel.id)).where(NodeModel.status == "active"),
        )
        unreachable = await self._scalar(
            session,
            select(func.count(NodeModel.id)).where(NodeModel.status == "unreachable"),
        )
        return DashboardNodeStatsDTO(
            total=total, active=active, unreachable=unreachable
        )

    @staticmethod
    def _count_docker() -> DashboardDockerStatsDTO:
        # TODO: implement real Docker container stats via DockerRuntime
        return DashboardDockerStatsDTO(total=0, running=0, stopped=0)

    async def _count_scripts(self, session: AsyncSession) -> DashboardEntityStatsDTO:
        total = await self._scalar(session, select(func.count(ScriptModel.id)))
        return DashboardEntityStatsDTO(total=total)

    async def _count_commands(self, session: AsyncSession) -> DashboardEntityStatsDTO:
        total = await self._scalar(session, select(func.count(CommandModel.id)))
        return DashboardEntityStatsDTO(total=total)

    async def _recent_activity(self) -> tuple[DashboardRecentActivityDTO, ...]:
        from app.application.dto.audit import AuditLogQueryDTO

        query = AuditLogQueryDTO(offset=0, limit=10)
        page = await self._audit_gateway.list_logs(query)
        return tuple(
            DashboardRecentActivityDTO(
                id=str(item.id),
                action=item.action,
                node_id=str(item.node_id) if item.node_id else None,
                user=item.user,
                details=item.details,
                created_at=item.created_at,
            )
            for item in page.items
        )

    @staticmethod
    async def _scalar(session: AsyncSession, stmt: Any) -> int:
        result = await session.execute(stmt)
        return result.scalar_one()
