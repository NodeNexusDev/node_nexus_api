from __future__ import annotations

from typing import Protocol

from app.application.dto.execution_stats import (
    CommandStatsQueryDTO,
    ExecutionStatsDTO,
    ScriptStatsQueryDTO,
)


class ExecutionStatsReader(Protocol):
    async def get_command_stats(
        self,
        query: CommandStatsQueryDTO,
    ) -> ExecutionStatsDTO: ...

    async def get_script_stats(
        self,
        query: ScriptStatsQueryDTO,
    ) -> ExecutionStatsDTO: ...

    async def get_node_command_stats(
        self,
        query: CommandStatsQueryDTO,
    ) -> ExecutionStatsDTO: ...

    async def get_node_script_stats(
        self,
        query: ScriptStatsQueryDTO,
    ) -> ExecutionStatsDTO: ...
