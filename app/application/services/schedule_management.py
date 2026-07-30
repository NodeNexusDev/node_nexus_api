"""Application use case for persistent schedule management."""

from uuid import UUID

from app.application.dto.schedule import (
    RuntimeScheduleDTO,
    ScheduleRequestDTO,
    ScheduleViewDTO,
)
from app.application.ports.node_management import NodeManagementReader
from app.application.ports.schedule import (
    JobSchedulerPort,
    ScheduleReader,
    ScheduleWriter,
)
from app.application.ports.script_persistence import ScriptReader
from app.core.exceptions import (
    NodeNotFoundError,
    ScheduleNotFoundError,
    SchedulePersistenceError,
    ScheduleValidationError,
    ScriptNotFoundError,
)


class ScheduleManagementService:
    """Manage desired schedules and apply their runtime projection."""

    def __init__(
        self,
        reader: ScheduleReader,
        writer: ScheduleWriter,
        script_reader: ScriptReader,
        node_reader: NodeManagementReader,
        scheduler: JobSchedulerPort,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._script_reader = script_reader
        self._node_reader = node_reader
        self._scheduler = scheduler

    async def create_or_update(
        self, script_id: UUID, data: ScheduleRequestDTO
    ) -> ScheduleViewDTO:
        if await self._script_reader.get_script(script_id) is None:
            raise ScriptNotFoundError("Script not found")
        try:
            self._scheduler.validate(data.cron, data.timezone)
        except (KeyError, RuntimeError, ValueError) as exc:
            raise ScheduleValidationError(
                "Invalid cron expression or timezone"
            ) from exc
        for node_id in data.node_ids:
            if await self._node_reader.get_node(node_id) is None:
                raise NodeNotFoundError(f"Node {node_id} not found")

        desired = await self._writer.upsert_schedule(script_id, data)
        try:
            runtime = self._scheduler.add_or_replace(self._to_runtime(desired))
        except (RuntimeError, ValueError) as exc:
            await self._writer.mark_registration(
                script_id,
                state="registration_failed",
                error_type=type(exc).__name__,
            )
            raise SchedulePersistenceError(
                "Schedule was saved but runtime registration failed"
            ) from exc
        await self._writer.mark_registration(
            script_id,
            state="registered",
            error_type=None,
            next_run_at=runtime.next_run_at,
        )
        registered = await self._reader.get_schedule(script_id)
        return registered or desired

    async def get(self, script_id: UUID) -> ScheduleViewDTO:
        schedule = await self._reader.get_schedule(script_id)
        if schedule is None:
            raise ScheduleNotFoundError("No schedule found for script")
        return schedule

    async def delete(self, script_id: UUID) -> None:
        if not await self._writer.delete_schedule(script_id):
            raise ScheduleNotFoundError("No schedule found for script")
        self._scheduler.remove(script_id)

    @staticmethod
    def _to_runtime(schedule: ScheduleViewDTO) -> RuntimeScheduleDTO:
        return RuntimeScheduleDTO(
            schedule_id=schedule.id,
            script_id=schedule.script_id,
            cron=schedule.cron,
            timezone=schedule.timezone,
            node_ids=schedule.node_ids,
            params=schedule.params,
            misfire_grace_seconds=schedule.misfire_grace_seconds,
        )
