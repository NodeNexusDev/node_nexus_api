from __future__ import annotations

import uuid
from datetime import datetime

from app.application.dto.execution_stats import (
    CommandStatsQueryDTO,
    ExecutionStatsDTO,
    ScriptStatsQueryDTO,
)
from app.application.ports.execution_stats import ExecutionStatsReader


class ExecutionStatsService:
    def __init__(self, reader: ExecutionStatsReader) -> None:
        self._reader = reader

    async def get_command_stats(
        self,
        command_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ExecutionStatsDTO:
        query = CommandStatsQueryDTO(
            command_id=command_id,
            node_id=node_id,
            date_from=date_from,
            date_to=date_to,
        )
        return await self._reader.get_command_stats(query)

    async def get_script_stats(
        self,
        script_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ExecutionStatsDTO:
        query = ScriptStatsQueryDTO(
            script_id=script_id,
            node_id=node_id,
            date_from=date_from,
            date_to=date_to,
        )
        return await self._reader.get_script_stats(query)

    async def get_node_command_stats(
        self,
        node_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ExecutionStatsDTO:
        query = CommandStatsQueryDTO(
            node_id=node_id,
            date_from=date_from,
            date_to=date_to,
        )
        return await self._reader.get_node_command_stats(query)

    async def get_node_script_stats(
        self,
        node_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ExecutionStatsDTO:
        query = ScriptStatsQueryDTO(
            node_id=node_id,
            date_from=date_from,
            date_to=date_to,
        )
        return await self._reader.get_node_script_stats(query)
