from __future__ import annotations

from typing import Protocol

from app.application.dto.dashboard_metrics import (
    DashboardMetricsDTO,
    MetricsQueryDTO,
)


class DashboardMetricsReader(Protocol):
    async def get_metrics(
        self,
        query: MetricsQueryDTO,
    ) -> DashboardMetricsDTO: ...
