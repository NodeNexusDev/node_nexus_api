from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.application.dto.dashboard_metrics import (
    DashboardMetricsDTO,
    MetricsQueryDTO,
)
from app.application.ports.dashboard_metrics import DashboardMetricsReader


class DashboardMetricsService:
    def __init__(self, reader: DashboardMetricsReader) -> None:
        self._reader = reader

    async def get_metrics(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        group_by: Literal["day", "hour", "week", "month"] = "day",
    ) -> DashboardMetricsDTO:
        return await self._reader.get_metrics(
            MetricsQueryDTO(
                date_from=date_from,
                date_to=date_to,
                group_by=group_by,
            ),
        )
