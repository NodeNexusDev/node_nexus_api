"""Short-scope SQLAlchemy adapter for command execution history ports."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.command_execution import CommandExecutionRepository
from app.application.dto.command_history import (
    CommandHistoryCreateDTO,
    CommandHistoryDTO,
    CommandHistoryPageDTO,
    CommandHistoryQueryDTO,
)
from app.models.command_execution import CommandExecutionModel


class SqlAlchemyCommandHistoryGateway:
    """Implement command history read/write ports with operation-local sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def save(self, data: CommandHistoryCreateDTO) -> CommandHistoryDTO:
        """Persist a command execution record in a short transaction."""
        async with self._sessionmaker.begin() as session:
            execution = await CommandExecutionRepository(session).create(
                {
                    "node_id": data.node_id,
                    "command_id": data.command_id,
                    "command_fingerprint": data.command_fingerprint,
                    "exit_code": data.exit_code,
                    "stdout": data.stdout,
                    "stderr": data.stderr,
                    "stdout_bytes": data.stdout_bytes,
                    "stderr_bytes": data.stderr_bytes,
                    "truncated": data.truncated,
                    "started_at": data.started_at,
                    "finished_at": data.finished_at,
                }
            )
            return self._to_dto(execution)

    async def list_by_node(
        self, query: CommandHistoryQueryDTO
    ) -> CommandHistoryPageDTO:
        """Return one paginated page for a node outside the request scope."""
        async with self._sessionmaker() as session:
            repository = CommandExecutionRepository(session)
            executions = await repository.list_by_node(
                query.node_id,
                skip=query.offset,
                limit=query.limit,
            )
            total = await repository.count_by_node(query.node_id)
            return CommandHistoryPageDTO(
                items=tuple(self._to_dto(execution) for execution in executions),
                total=total,
            )

    async def get_by_id(self, execution_id: UUID) -> CommandHistoryDTO | None:
        """Return one execution record by ID."""
        async with self._sessionmaker() as session:
            execution = await CommandExecutionRepository(session).get_by_id(
                execution_id
            )
            return self._to_dto(execution) if execution is not None else None

    @staticmethod
    def _to_dto(execution: CommandExecutionModel) -> CommandHistoryDTO:
        """Map an ORM execution record to an immutable application DTO."""
        return CommandHistoryDTO(
            id=execution.id,
            node_id=execution.node_id,
            command_id=execution.command_id,
            command_fingerprint=execution.command_fingerprint,
            exit_code=execution.exit_code,
            stdout=execution.stdout or "",
            stderr=execution.stderr or "",
            stdout_bytes=execution.stdout_bytes or 0,
            stderr_bytes=execution.stderr_bytes or 0,
            truncated=execution.truncated,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            created_at=execution.created_at,
        )
