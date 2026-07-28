"""Short-scope SQLAlchemy adapters for script execution."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.script_definition import ScriptDefinitionDTO
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository


class ScopedScriptDefinitionReader:
    """Load a script DTO and close its session."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_definition(self, script_id: UUID) -> ScriptDefinitionDTO | None:
        async with self._sessionmaker() as session:
            script = await ScriptRepository(session).get_by_id(script_id)
            if script is None:
                return None
            return ScriptDefinitionDTO(id=script.id, steps=tuple(script.steps or []))


class ScopedScriptExecutionWriter:
    """Commit each execution state transition in a short transaction."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create_execution(self, data: dict[str, Any]) -> UUID:
        async with self._sessionmaker.begin() as session:
            execution = await ScriptExecutionRepository(session).create(data)
            return execution.id

    async def update_execution(self, execution_id: UUID, data: dict[str, Any]) -> None:
        async with self._sessionmaker.begin() as session:
            await ScriptExecutionRepository(session).update(execution_id, data)
