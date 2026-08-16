from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.dashboard_metrics import (
    DashboardMetricsRepository,
)
from app.application.dto.dashboard_metrics import (
    DashboardMetricsDTO,
    MetricsQueryDTO,
)


class SqlAlchemyDashboardMetricsGateway:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._sessionmaker = sessionmaker

    async def get_metrics(
        self, query: MetricsQueryDTO,
    ) -> DashboardMetricsDTO:
        async with self._sessionmaker() as session:
            repo = DashboardMetricsRepository(session)
            cmd = await repo.command_metrics(query)
            scr = await repo.script_metrics(query)
            return DashboardMetricsDTO(
                command_metrics=tuple(cmd),
                script_metrics=tuple(scr),
            )
