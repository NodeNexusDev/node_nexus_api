"""Inbound use case invoked by the runtime scheduler adapter."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.application.dto.script_execution import ScriptExecutionRequestDTO
from app.application.ports.schedule import ScheduleWriter
from app.services.script_execution_service import ScriptExecutionService


class ScheduledScriptExecutor:
    """Execute one scheduled script and persist lifecycle metadata."""

    def __init__(
        self,
        script_execution: ScriptExecutionService,
        schedule_writer: ScheduleWriter,
    ) -> None:
        self._script_execution = script_execution
        self._schedule_writer = schedule_writer

    async def execute(
        self,
        script_id: UUID,
        node_ids: list[UUID],
        params: dict[str, Any],
    ) -> None:
        await self._schedule_writer.mark_started(script_id, datetime.now(UTC))
        try:
            await self._script_execution.execute_script(
                script_id,
                ScriptExecutionRequestDTO(
                    node_ids=tuple(node_ids),
                    params=tuple(params.items()),
                ),
            )
        except Exception as exc:
            await self._schedule_writer.mark_failed(
                script_id,
                datetime.now(UTC),
                type(exc).__name__,
            )
            raise
        await self._schedule_writer.mark_succeeded(script_id, datetime.now(UTC))
