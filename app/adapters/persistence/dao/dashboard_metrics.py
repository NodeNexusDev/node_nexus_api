from __future__ import annotations

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.dashboard_metrics import (
    MetricsBucketDTO,
    MetricsQueryDTO,
)
from app.models.command_execution import CommandExecutionModel
from app.models.script_execution import ScriptExecutionModel

_GROUP_MAP = {
    "day": "day",
    "hour": "hour",
    "week": "week",
    "month": "month",
}


class DashboardMetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def command_metrics(
        self,
        query: MetricsQueryDTO,
    ) -> list[MetricsBucketDTO]:
        grp = _GROUP_MAP.get(query.group_by, "day")
        trunc = func.date_trunc(grp, CommandExecutionModel.started_at)
        dur = (
            func.extract(
                text("epoch"),
                CommandExecutionModel.finished_at - CommandExecutionModel.started_at,
            )
            * 1000
        )
        ok = case((CommandExecutionModel.exit_code == 0, 1), else_=0)
        fail = case((CommandExecutionModel.exit_code != 0, 1), else_=0)
        stmt = select(
            trunc.label("period"),
            func.count().label("total"),
            func.sum(ok).label("successful"),
            func.sum(fail).label("failed"),
            func.avg(dur).label("avg_duration_ms"),
        ).group_by(trunc)
        if query.date_from is not None:
            stmt = stmt.where(
                CommandExecutionModel.started_at >= query.date_from,
            )
        if query.date_to is not None:
            stmt = stmt.where(
                CommandExecutionModel.started_at <= query.date_to,
            )
        stmt = stmt.order_by(trunc)
        rows = (await self._session.execute(stmt)).all()
        return [
            MetricsBucketDTO(
                period=str(row.period),
                total=row.total,
                successful=row.successful or 0,
                failed=row.failed or 0,
                avg_duration_ms=row.avg_duration_ms,
            )
            for row in rows
        ]

    async def script_metrics(
        self,
        query: MetricsQueryDTO,
    ) -> list[MetricsBucketDTO]:
        grp = _GROUP_MAP.get(query.group_by, "day")
        trunc = func.date_trunc(grp, ScriptExecutionModel.started_at)
        dur = (
            func.extract(
                text("epoch"),
                ScriptExecutionModel.finished_at - ScriptExecutionModel.started_at,
            )
            * 1000
        )
        ok = case((ScriptExecutionModel.status == "completed", 1), else_=0)
        fail = case((ScriptExecutionModel.status != "completed", 1), else_=0)
        stmt = select(
            trunc.label("period"),
            func.count().label("total"),
            func.sum(ok).label("successful"),
            func.sum(fail).label("failed"),
            func.avg(dur).label("avg_duration_ms"),
        ).group_by(trunc)
        if query.date_from is not None:
            stmt = stmt.where(
                ScriptExecutionModel.started_at >= query.date_from,
            )
        if query.date_to is not None:
            stmt = stmt.where(
                ScriptExecutionModel.started_at <= query.date_to,
            )
        stmt = stmt.order_by(trunc)
        rows = (await self._session.execute(stmt)).all()
        return [
            MetricsBucketDTO(
                period=str(row.period),
                total=row.total,
                successful=row.successful or 0,
                failed=row.failed or 0,
                avg_duration_ms=row.avg_duration_ms,
            )
            for row in rows
        ]
