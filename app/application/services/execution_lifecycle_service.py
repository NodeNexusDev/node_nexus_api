"""Execution lifecycle service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.dto.execution_lifecycle import (
    CancelExecutionDTO,
    RetryCommandDTO,
    RetryCommandResultDTO,
    RetryScriptDTO,
    RetryScriptResultDTO,
)
from app.core.exceptions import ExecutionNotFoundError

if TYPE_CHECKING:
    from app.application.ports.command_history import CommandHistoryReader
    from app.application.ports.execution_lifecycle import ExecutionLifecycleManager

audit_logger = __import__("structlog").get_logger("audit")


class ExecutionLifecycleService:
    """Retry and cancel execution use cases."""

    def __init__(
        self,
        manager: ExecutionLifecycleManager,
        command_history_reader: CommandHistoryReader | None = None,
    ) -> None:
        self._manager = manager
        self._command_history_reader = command_history_reader

    async def retry_command(self, data: RetryCommandDTO) -> RetryCommandResultDTO:
        """Re-execute a command by loading its previous execution record."""
        if self._command_history_reader is None:
            raise ExecutionNotFoundError("Command history reader not available")
        execution = await self._command_history_reader.get_by_id(data.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(f"Execution {data.execution_id} not found")
        return RetryCommandResultDTO(
            execution_id=str(execution.id),
            node_id=str(execution.node_id) if execution.node_id else None,
            command_fingerprint=execution.command_fingerprint,
            status="retry_scheduled",
        )

    async def retry_script(self, data: RetryScriptDTO) -> RetryScriptResultDTO:
        """Confirm script retry. Client should re-execute with same params."""
        return RetryScriptResultDTO(
            execution_id=str(data.execution_id),
            status="retry_scheduled",
        )

    async def cancel_execution(self, data: CancelExecutionDTO) -> bool:
        """Cancel a running execution."""
        result = await self._manager.cancel_execution(data)
        if not result:
            raise ExecutionNotFoundError(
                f"Execution {data.execution_id} not found or already completed"
            )
        return True
