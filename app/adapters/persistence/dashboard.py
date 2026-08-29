"""SQLAlchemy adapter for the dashboard reader port."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import Executable, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.audit import SqlAlchemyAuditLogGateway
from app.application.dto.dashboard import (
    DashboardDockerStatsDTO,
    DashboardDTO,
    DashboardEntityStatsDTO,
    DashboardNodeStatsDTO,
    DashboardRecentActivityDTO,
)
from app.application.services.docker.command_builder import build_docker_command
from app.application.services.docker.parsers import json_string, parse_json_lines
from app.models.command import CommandModel
from app.models.node import NodeModel
from app.models.script import ScriptModel

if TYPE_CHECKING:
    from app.application.dto.node_connection import NodeConnectionDTO
    from app.application.ports.docker_runtime import DockerRuntime
    from app.application.ports.node_reader import NodeConnectionReader

log = structlog.get_logger("dashboard")


class SqlAlchemyDashboardGateway:
    """Aggregate dashboard statistics from existing tables and Docker nodes."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        node_reader: NodeConnectionReader | None = None,
        runtime: DockerRuntime | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._audit_gateway = SqlAlchemyAuditLogGateway(sessionmaker)
        self._node_reader = node_reader
        self._runtime = runtime

    async def get_dashboard(self) -> DashboardDTO:
        async with self._sessionmaker() as session:
            nodes = await self._count_nodes(session)
            scripts = await self._count_scripts(session)
            commands = await self._count_commands(session)
        docker = await self._count_docker()
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

    async def _count_docker(self) -> DashboardDockerStatsDTO:
        if self._node_reader is None or self._runtime is None:
            return DashboardDockerStatsDTO(total=0, running=0, stopped=0)

        try:
            docker_nodes = await self._get_docker_nodes()
        except Exception:
            log.warning("dashboard.docker_nodes_query_failed")
            return DashboardDockerStatsDTO(total=0, running=0, stopped=0)

        total = 0
        running = 0
        stopped = 0

        for node in docker_nodes:
            try:
                counts = await self._query_node_containers(node)
                total += counts["total"]
                running += counts["running"]
                stopped += counts["stopped"]
            except Exception:
                log.warning(
                    "dashboard.docker_query_failed",
                    node_id=str(node.id),
                    node_name=node.name,
                )

        return DashboardDockerStatsDTO(total=total, running=running, stopped=stopped)

    async def _get_docker_nodes(self) -> list[NodeConnectionDTO]:
        """Fetch nodes with docker capability."""
        try:
            async with self._sessionmaker() as session:
                result = await session.execute(
                    select(NodeModel).where(NodeModel.has_docker.is_(True))
                )
                models = list(result.scalars().all())
                if models:
                    from app.adapters.persistence.dao.node import NodeRepository

                    return [NodeRepository._to_connection_dto(m) for m in models]
        except Exception:
            log.warning("dashboard.docker_has_docker_query_failed")
        # Fallback for tests / legacy mocks
        if self._node_reader is not None:
            try:
                legacy = await self._node_reader.get_connections_by_type("docker")
                if legacy:
                    return legacy
            except Exception:
                pass
            try:
                all_ssh = await self._node_reader.get_connections_by_type("ssh")
                return [n for n in all_ssh if getattr(n, "is_docker_available", False)]
            except Exception:
                pass
        return []

    async def _query_node_containers(self, node: NodeConnectionDTO) -> dict[str, int]:
        """Query container stats from a single Docker node."""
        cmd = build_docker_command(node, "ps -a --format '{{json .}}'")
        if self._runtime is None:
            return {"total": 0, "running": 0, "stopped": 0}
        result = await self._runtime.execute(node, cmd, timeout=10)

        if result.exit_code != 0:
            return {"total": 0, "running": 0, "stopped": 0}

        items = parse_json_lines(result.stdout)
        total = len(items)
        running = sum(1 for item in items if json_string(item, "State") == "running")
        stopped = total - running
        return {"total": total, "running": running, "stopped": stopped}

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
    async def _scalar(session: AsyncSession, stmt: Executable) -> int:
        result = await session.execute(stmt)
        return int(result.scalar_one())
