"""Short-scope SQLAlchemy command template reader."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.command import CommandRepository
from app.application.dto.command_template import CommandTemplateDTO


class ScopedCommandTemplateReader:
    """Load a command DTO and close its session before remote I/O."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_template(self, command_id: UUID) -> CommandTemplateDTO | None:
        async with self._sessionmaker() as session:
            command = await CommandRepository(session).get_by_id(command_id)
            if command is None:
                return None
            return CommandTemplateDTO(
                id=command.id,
                command=command.command,
                parameters=tuple(command.parameters or []),
            )
