"""Script execution history application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.application.dto.script_execution import (
    ScriptExecutionDTO,
    ScriptExecutionQueryDTO,
)
from app.core.exceptions import ScriptNotFoundError

if TYPE_CHECKING:
    from app.application.ports.script_persistence import (
        ScriptExecutionReader,
        ScriptReader,
    )


class ScriptHistoryService:
    """Query execution history without exposing persistence objects."""

    def __init__(
        self,
        script_reader: ScriptReader,
        execution_reader: ScriptExecutionReader,
    ) -> None:
        self._script_reader = script_reader
        self._execution_reader = execution_reader

    async def get_executions(
        self, script_id: UUID, page: int = 1, size: int = 20
    ) -> tuple[list[ScriptExecutionDTO], int]:
        if await self._script_reader.get_script(script_id) is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")
        result = await self._execution_reader.list_executions(
            ScriptExecutionQueryDTO(
                script_id=script_id,
                offset=(page - 1) * size,
                limit=size,
            )
        )
        return list(result.items), result.total
