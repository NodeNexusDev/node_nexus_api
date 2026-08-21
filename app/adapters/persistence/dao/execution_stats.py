from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULT_STATS: dict[str, Any] = {
    "total": 0,
    "successful": 0,
    "failed": 0,
    "avg_duration_ms": None,
    "min_duration_ms": None,
    "max_duration_ms": None,
    "last_executed_at": None,
}


class ExecutionStatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def command_stats(
        self,
        command_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        where_clauses: list[str] = []
        if command_id is not None:
            where_clauses.append("ce.command_id = :command_id")
            params["command_id"] = command_id
        if node_id is not None:
            where_clauses.append("ce.node_id = :node_id")
            params["node_id"] = node_id
        if date_from is not None:
            where_clauses.append("ce.started_at >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            where_clauses.append("ce.started_at <= :date_to")
            params["date_to"] = date_to

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        dur = "EXTRACT(EPOCH FROM (ce.finished_at - ce.started_at)) * 1000"
        sql = text(  # nosec B608: false positive – dur/where_sql built from whitelisted constants
            "SELECT "
            "  COUNT(*)::int AS total, "
            "  COUNT(*) FILTER (WHERE ce.exit_code = 0)::int AS successful, "  # noqa: E501
            "  COUNT(*) FILTER (WHERE ce.exit_code != 0)::int AS failed, "  # noqa: E501
            f"  AVG({dur}) AS avg_duration_ms, "  # nosec B608
            f"  MIN({dur}) AS min_duration_ms, "  # nosec B608
            f"  MAX({dur}) AS max_duration_ms, "  # nosec B608
            "  MAX(ce.finished_at) AS last_executed_at "
            "FROM command_executions ce "
            f"WHERE {where_sql}"  # nosec B608
        )
        row = (await self._session.execute(sql, params)).one_or_none()
        return dict(row._mapping) if row else dict(_DEFAULT_STATS)

    async def script_stats(
        self,
        script_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        where_clauses: list[str] = []
        if script_id is not None:
            where_clauses.append("se.script_id = :script_id")
            params["script_id"] = script_id
        if node_id is not None:
            where_clauses.append("se.node_id = :node_id")
            params["node_id"] = node_id
        if date_from is not None:
            where_clauses.append("se.started_at >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            where_clauses.append("se.started_at <= :date_to")
            params["date_to"] = date_to

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        dur = "EXTRACT(EPOCH FROM (se.finished_at - se.started_at)) * 1000"
        sql = text(  # nosec B608: false positive – dur/where_sql built from whitelisted constants
            "SELECT "
            "  COUNT(*)::int AS total, "
            "  COUNT(*) FILTER (WHERE se.status = 'completed')::int AS successful, "  # noqa: E501
            "  COUNT(*) FILTER (WHERE se.status != 'completed')::int AS failed, "  # noqa: E501
            f"  AVG({dur}) AS avg_duration_ms, "  # nosec B608
            f"  MIN({dur}) AS min_duration_ms, "  # nosec B608
            f"  MAX({dur}) AS max_duration_ms, "  # nosec B608
            "  MAX(se.finished_at) AS last_executed_at "
            "FROM script_executions se "
            f"WHERE {where_sql}"  # nosec B608
        )
        row = (await self._session.execute(sql, params)).one_or_none()
        return dict(row._mapping) if row else dict(_DEFAULT_STATS)
