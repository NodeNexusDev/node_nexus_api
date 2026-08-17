from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.dashboard_metrics import (
    MetricsBucketDTO,
    MetricsQueryDTO,
)

_GROUP_MAP = {
    "day": "day",
    "hour": "hour",
    "week": "week",
    "month": "month",
}

_DUR = "EXTRACT(EPOCH FROM ({t}.finished_at - {t}.started_at)) * 1000"


class DashboardMetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def command_metrics(
        self,
        query: MetricsQueryDTO,
    ) -> list[MetricsBucketDTO]:
        grp = _GROUP_MAP[query.group_by]
        params: dict = {"grp": grp}
        where_clauses: list[str] = []
        if query.date_from is not None:
            where_clauses.append("ce.started_at >= :date_from")
            params["date_from"] = query.date_from
        if query.date_to is not None:
            where_clauses.append("ce.started_at <= :date_to")
            params["date_to"] = query.date_to

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        dur = _DUR.format(t="ce")
        sql = text(  # nosec B608: false positive – dur/where_sql built from whitelisted constants
            "SELECT "
            f"  date_trunc(:grp, ce.started_at) AS period, "  # nosec B608
            "  COUNT(*)::int AS total, "
            "  COUNT(*) FILTER (WHERE ce.exit_code = 0)::int AS successful, "  # noqa: E501
            "  COUNT(*) FILTER (WHERE ce.exit_code != 0)::int AS failed, "  # noqa: E501
            f"  AVG({dur}) AS avg_duration_ms "  # nosec B608
            "FROM command_executions ce "
            f"WHERE {where_sql} "  # nosec B608
            f"GROUP BY date_trunc(:grp, ce.started_at) "  # nosec B608
            f"ORDER BY date_trunc(:grp, ce.started_at)"  # nosec B608
        )
        rows = (await self._session.execute(sql, params)).all()
        return [
            MetricsBucketDTO(
                period=str(row.period),
                total=row.total,
                successful=row.successful,
                failed=row.failed,
                avg_duration_ms=row.avg_duration_ms,
            )
            for row in rows
        ]

    async def script_metrics(
        self,
        query: MetricsQueryDTO,
    ) -> list[MetricsBucketDTO]:
        grp = _GROUP_MAP[query.group_by]
        params: dict = {"grp": grp}
        where_clauses: list[str] = []
        if query.date_from is not None:
            where_clauses.append("se.started_at >= :date_from")
            params["date_from"] = query.date_from
        if query.date_to is not None:
            where_clauses.append("se.started_at <= :date_to")
            params["date_to"] = query.date_to

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        dur = _DUR.format(t="se")
        sql = text(  # nosec B608: false positive – dur/where_sql built from whitelisted constants
            "SELECT "
            f"  date_trunc(:grp, se.started_at) AS period, "  # nosec B608
            "  COUNT(*)::int AS total, "
            "  COUNT(*) FILTER (WHERE se.status = 'completed')::int AS successful, "  # noqa: E501
            "  COUNT(*) FILTER (WHERE se.status != 'completed')::int AS failed, "  # noqa: E501
            f"  AVG({dur}) AS avg_duration_ms "  # nosec B608
            "FROM script_executions se "
            f"WHERE {where_sql} "  # nosec B608
            f"GROUP BY date_trunc(:grp, se.started_at) "  # nosec B608
            f"ORDER BY date_trunc(:grp, se.started_at)"  # nosec B608
        )
        rows = (await self._session.execute(sql, params)).all()
        return [
            MetricsBucketDTO(
                period=str(row.period),
                total=row.total,
                successful=row.successful,
                failed=row.failed,
                avg_duration_ms=row.avg_duration_ms,
            )
            for row in rows
        ]
