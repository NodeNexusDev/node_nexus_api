"""Inbound use case invoked by the runtime scheduler adapter."""

from datetime import UTC, datetime
from uuid import UUID

from app.application.dto.script_execution import ScriptExecutionRequestDTO
from app.application.ports.schedule import ScheduleWriter
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.types import JsonValue
from app.core.exceptions import ScheduledScriptExecutionError


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
        params: dict[str, JsonValue],
        schedule_id: UUID | None = None,
    ) -> None:
        await self._schedule_writer.mark_started(script_id, datetime.now(UTC))
        try:
            result = await self._script_execution.execute_script(
                script_id,
                ScriptExecutionRequestDTO(
                    node_ids=tuple(node_ids),
                    params=tuple(params.items()),
                    trigger="scheduled",
                    schedule_id=schedule_id,
                ),
            )
        except Exception as exc:
            await self._schedule_writer.mark_failed(
                script_id,
                datetime.now(UTC),
                type(exc).__name__,
            )
            raise

        if any(node_result.status == "error" for node_result in result.results):
            error_type = ScheduledScriptExecutionError.__name__
            await self._schedule_writer.mark_failed(
                script_id,
                datetime.now(UTC),
                error_type,
            )
            raise ScheduledScriptExecutionError(
                f"Scheduled script {script_id} reported a failed execution"
            )

        await self._schedule_writer.mark_succeeded(script_id, datetime.now(UTC))
