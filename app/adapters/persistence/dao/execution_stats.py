from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.execution_stats import ExecutionStatsRow

_DEFAULT_STATS: ExecutionStatsRow = {
    "total": 0,
    "successful": 0,
    "failed": 0,
    "cancelled": 0,
    "avg_duration_ms": None,
    "min_duration_ms": None,
    "max_duration_ms": None,
    "last_executed_at": None,
}


def _empty_stats() -> ExecutionStatsRow:
    return ExecutionStatsRow(
        total=0,
        successful=0,
        failed=0,
        cancelled=0,
        avg_duration_ms=None,
        min_duration_ms=None,
        max_duration_ms=None,
        last_executed_at=None,
    )


_SCRIPT_TERMINAL_STATUSES = "('success', 'error', 'completed', 'failed')"
_SCRIPT_SUCCESS_STATUSES = "('success', 'completed')"
_SCRIPT_FAILURE_STATUSES = "('error', 'failed')"
_SCRIPT_CANCELLED_STATUSES = "('cancelled')"


class ExecutionStatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def command_stats(
        self,
        command_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ExecutionStatsRow:
        params: dict[str, object] = {}
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
            where_clauses.append("ce.started_at < :date_to")
            params["date_to"] = date_to

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        dur = "GREATEST(0, EXTRACT(EPOCH FROM (ce.finished_at - ce.started_at)) * 1000)"
        # command_executions: no cancelled status — always 0 (unlike scripts)
        sql = text(  # nosec B608: false positive – dur/where_sql built from whitelisted constants
            "SELECT "
            "  COUNT(*)::int AS total, "
            "  COUNT(*) FILTER (WHERE ce.exit_code = 0)::int AS successful, "  # noqa: E501
            "  COUNT(*) FILTER (WHERE ce.exit_code != 0)::int AS failed, "  # noqa: E501
            "  0::int AS cancelled, "  # noqa: E501 — no cancelled for commands
            f"  AVG({dur}) FILTER (WHERE ce.finished_at IS NOT NULL) AS avg_duration_ms, "  # noqa: E501  # nosec B608
            f"  MIN({dur}) FILTER (WHERE ce.finished_at IS NOT NULL) AS min_duration_ms, "  # noqa: E501  # nosec B608
            f"  MAX({dur}) FILTER (WHERE ce.finished_at IS NOT NULL) AS max_duration_ms, "  # noqa: E501  # nosec B608
            "  MAX(ce.finished_at) AS last_executed_at "
            "FROM command_executions ce "
            f"WHERE {where_sql}"  # nosec B608
        )
        row = (await self._session.execute(sql, params)).one_or_none()
        return self._validated_row(row._mapping) if row else _empty_stats()

    async def script_stats(
        self,
        script_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ExecutionStatsRow:
        params: dict[str, object] = {}
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
            where_clauses.append("se.started_at < :date_to")
            params["date_to"] = date_to

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        dur = "GREATEST(0, EXTRACT(EPOCH FROM (se.finished_at - se.started_at)) * 1000)"
        sql = text(  # nosec B608: false positive – dur/where_sql built from whitelisted constants
            "SELECT "
            f"  COUNT(*) FILTER (WHERE se.status IN {_SCRIPT_TERMINAL_STATUSES})::int AS total, "  # nosec B608  # noqa: E501
            f"  COUNT(*) FILTER (WHERE se.status IN {_SCRIPT_SUCCESS_STATUSES})::int AS successful, "  # nosec B608  # noqa: E501
            f"  COUNT(*) FILTER (WHERE se.status IN {_SCRIPT_FAILURE_STATUSES})::int AS failed, "  # nosec B608  # noqa: E501
            f"  COUNT(*) FILTER (WHERE se.status IN {_SCRIPT_CANCELLED_STATUSES})::int AS cancelled, "  # nosec B608  # noqa: E501
            f"  AVG({dur}) FILTER (WHERE se.status IN {_SCRIPT_TERMINAL_STATUSES}) AS avg_duration_ms, "  # nosec B608  # noqa: E501
            f"  MIN({dur}) FILTER (WHERE se.status IN {_SCRIPT_TERMINAL_STATUSES}) AS min_duration_ms, "  # nosec B608  # noqa: E501
            f"  MAX({dur}) FILTER (WHERE se.status IN {_SCRIPT_TERMINAL_STATUSES}) AS max_duration_ms, "  # nosec B608  # noqa: E501
            f"  MAX(se.finished_at) FILTER (WHERE se.status IN {_SCRIPT_TERMINAL_STATUSES}) AS last_executed_at "  # nosec B608  # noqa: E501
            "FROM script_executions se "
            f"WHERE {where_sql}"  # nosec B608
        )
        row = (await self._session.execute(sql, params)).one_or_none()
        return self._validated_row(row._mapping) if row else _empty_stats()

    @staticmethod
    def _validated_row(row: Mapping[object, object] | RowMapping) -> ExecutionStatsRow:
        """Validate the untyped SQL driver boundary before returning it."""

        def required_int(name: str) -> int:
            value = row.get(name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"Statistics field {name!r} must be an integer")
            return value

        def optional_float(name: str) -> float | None:
            value = row.get(name)
            if value is None:
                return None
            if not isinstance(value, int | float | Decimal) or isinstance(value, bool):
                raise TypeError(f"Statistics field {name!r} must be numeric or null")
            return float(value)

        last_executed_at = row.get("last_executed_at")
        if last_executed_at is not None and not isinstance(last_executed_at, datetime):
            raise TypeError("Statistics last_executed_at must be a datetime or null")

        return ExecutionStatsRow(
            total=required_int("total"),
            successful=required_int("successful"),
            failed=required_int("failed"),
            cancelled=required_int("cancelled"),
            avg_duration_ms=optional_float("avg_duration_ms"),
            min_duration_ms=optional_float("min_duration_ms"),
            max_duration_ms=optional_float("max_duration_ms"),
            last_executed_at=last_executed_at,
        )
