from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.execution_stats import ExecutionStatsRepository
from app.application.dto.execution_stats import (
    CommandStatsQueryDTO,
    ExecutionStatsDTO,
    ScriptStatsQueryDTO,
)


class SqlAlchemyExecutionStatsGateway:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._sessionmaker = sessionmaker

    async def get_command_stats(
        self,
        query: CommandStatsQueryDTO,
    ) -> ExecutionStatsDTO:
        async with self._sessionmaker() as session:
            repo = ExecutionStatsRepository(session)
            row = await repo.command_stats(
                command_id=query.command_id,
                node_id=query.node_id,
                date_from=query.date_from,
                date_to=query.date_to,
            )
            return self._to_stats_dto(row)

    async def get_script_stats(
        self,
        query: ScriptStatsQueryDTO,
    ) -> ExecutionStatsDTO:
        async with self._sessionmaker() as session:
            repo = ExecutionStatsRepository(session)
            row = await repo.script_stats(
                script_id=query.script_id,
                node_id=query.node_id,
                date_from=query.date_from,
                date_to=query.date_to,
            )
            return self._to_stats_dto(row)

    async def get_node_command_stats(
        self,
        query: CommandStatsQueryDTO,
    ) -> ExecutionStatsDTO:
        return await self.get_command_stats(query)

    async def get_node_script_stats(
        self,
        query: ScriptStatsQueryDTO,
    ) -> ExecutionStatsDTO:
        return await self.get_script_stats(query)

    @staticmethod
    def _to_stats_dto(row: dict) -> ExecutionStatsDTO:
        total = row["total"] or 0
        successful = row["successful"] or 0
        failed = row["failed"] or 0
        return ExecutionStatsDTO(
            total=total,
            successful=successful,
            failed=failed,
            success_rate=successful / total if total > 0 else 0.0,
            avg_duration_ms=row["avg_duration_ms"],
            min_duration_ms=row["min_duration_ms"],
            max_duration_ms=row["max_duration_ms"],
            last_executed_at=row["last_executed_at"],
        )
