"""Short-scope SQLAlchemy adapter for execution lifecycle ports."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.command_execution import CommandExecutionRepository
from app.adapters.persistence.dao.script_execution import ScriptExecutionRepository
from app.application.dto.execution_lifecycle import (
    CancelExecutionDTO,
)


class SqlAlchemyExecutionLifecycleGateway:
    """Implement execution lifecycle ports with operation-local sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def cancel_execution(self, data: CancelExecutionDTO) -> bool:
        """Mark an execution as cancelled."""
        async with self._sessionmaker.begin() as session:
            # Try command execution first
            cmd_repo = CommandExecutionRepository(session)
            execution = await cmd_repo.get_by_id(data.execution_id)
            if execution is not None:
                # Command executions are append-only; acknowledge cancel request
                return True

            # Try script execution
            script_repo = ScriptExecutionRepository(session)
            execution = await script_repo.get_by_id(data.execution_id)
            if execution is not None:
                if execution.status in ("pending", "running"):
                    await script_repo.update(data.execution_id, {"status": "cancelled"})
                    return True
                return False

            return False
