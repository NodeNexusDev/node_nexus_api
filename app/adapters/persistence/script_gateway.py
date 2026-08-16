"""Short-scope SQLAlchemy adapters for script execution."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.script import ScriptRepository
from app.adapters.persistence.dao.script_execution import ScriptExecutionRepository
from app.application.dto.script_definition import ScriptDefinitionDTO
from app.application.dto.script_execution import (
    ScriptExecutionDTO,
    ScriptExecutionPageDTO,
    ScriptExecutionQueryDTO,
    ScriptStepResultDTO,
)
from app.application.dto.script_management import (
    ScriptCreateDTO,
    ScriptListQueryDTO,
    ScriptPageDTO,
    ScriptStepDTO,
    ScriptUpdateDTO,
    ScriptViewDTO,
)
from app.models.script import ScriptModel
from app.models.script_execution import ScriptExecutionModel


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


class SqlAlchemyScriptGateway:
    """Implement script management, definition, and history ports."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_script(self, script_id: UUID) -> ScriptViewDTO | None:
        async with self._sessionmaker() as session:
            script = await ScriptRepository(session).get_by_id(script_id)
            return self._to_view(script) if script is not None else None

    async def list_scripts(self, query: ScriptListQueryDTO) -> ScriptPageDTO:
        async with self._sessionmaker() as session:
            repository = ScriptRepository(session)
            tags = list(query.tags) or None
            scripts = await repository.get_all(
                skip=query.offset,
                limit=query.limit,
                tags=tags,
                search=query.search,
            )
            total = await repository.count(tags=tags, search=query.search)
            return ScriptPageDTO(
                items=tuple(self._to_view(script) for script in scripts),
                total=total,
            )

    async def list_tags(self) -> list[str]:
        """Return all unique script tags."""
        async with self._sessionmaker() as session:
            return await ScriptRepository(session).get_all_tags()

    async def create_script(self, data: ScriptCreateDTO) -> ScriptViewDTO:
        async with self._sessionmaker.begin() as session:
            script = await ScriptRepository(session).create(
                {
                    "name": data.name,
                    "description": data.description,
                    "steps": [self._step_to_dict(step) for step in data.steps],
                    "tags": list(data.tags),
                }
            )
            return self._to_view(script)

    async def update_script(
        self, script_id: UUID, data: ScriptUpdateDTO
    ) -> ScriptViewDTO | None:
        changes: dict[str, object] = dict(data.changes)
        steps = changes.get("steps")
        if isinstance(steps, tuple):
            step_dtos = cast(tuple[ScriptStepDTO, ...], steps)
            changes["steps"] = [self._step_to_dict(step) for step in step_dtos]
        tags = changes.get("tags")
        if isinstance(tags, tuple):
            changes["tags"] = list(tags)
        async with self._sessionmaker.begin() as session:
            script = await ScriptRepository(session).update(script_id, changes)
            return self._to_view(script) if script is not None else None

    async def delete_script(self, script_id: UUID) -> bool:
        async with self._sessionmaker.begin() as session:
            script = await ScriptRepository(session).get_by_id(script_id)
            if script is None:
                return False
            await session.delete(script)
            await session.flush()
            return True

    async def get_definition(self, script_id: UUID) -> ScriptDefinitionDTO | None:
        async with self._sessionmaker() as session:
            script = await ScriptRepository(session).get_by_id(script_id)
            if script is None:
                return None
            return ScriptDefinitionDTO(id=script.id, steps=tuple(script.steps or ()))

    async def list_executions(
        self, query: ScriptExecutionQueryDTO
    ) -> ScriptExecutionPageDTO:
        async with self._sessionmaker() as session:
            repository = ScriptExecutionRepository(session)
            executions = await repository.get_by_script_id(
                query.script_id,
                skip=query.offset,
                limit=query.limit,
                trigger=query.trigger,
            )
            total = await repository.count_by_script_id(
                query.script_id, trigger=query.trigger
            )
            return ScriptExecutionPageDTO(
                items=tuple(self._to_execution(item) for item in executions),
                total=total,
            )

    @classmethod
    def _to_view(cls, script: ScriptModel) -> ScriptViewDTO:
        return ScriptViewDTO(
            id=script.id,
            name=script.name,
            description=script.description,
            steps=tuple(cls._step_from_dict(step) for step in script.steps),
            tags=tuple(script.tags or ()),
            created_at=script.created_at,
            updated_at=script.updated_at,
        )

    @staticmethod
    def _step_from_dict(step: dict[str, Any]) -> ScriptStepDTO:
        return ScriptStepDTO(
            label=step["label"],
            type=step["type"],
            command=step.get("command"),
            command_id=UUID(step["command_id"]) if step.get("command_id") else None,
            params=tuple((step.get("params") or {}).items()),
            on_failure=step.get("on_failure", "stop"),
        )

    @staticmethod
    def _step_to_dict(step: ScriptStepDTO) -> dict[str, Any]:
        return {
            "label": step.label,
            "type": step.type,
            "command": step.command,
            "command_id": str(step.command_id) if step.command_id else None,
            "params": dict(step.params),
            "on_failure": step.on_failure,
        }

    @staticmethod
    def _to_execution(execution: ScriptExecutionModel) -> ScriptExecutionDTO:
        step_results = tuple(
            ScriptStepResultDTO(
                step_index=step["step_index"],
                label=step["label"],
                command_fingerprint=step["command_fingerprint"],
                stdout=step["stdout"],
                stderr=step["stderr"],
                stdout_bytes=step["stdout_bytes"],
                stderr_bytes=step["stderr_bytes"],
                truncated=step.get("truncated", False),
                exit_code=step["exit_code"],
            )
            for step in (execution.steps or ())
        )
        return ScriptExecutionDTO(
            id=execution.id,
            script_id=execution.script_id,
            node_id=execution.node_id,
            params=tuple((execution.params or {}).items()),
            status=execution.status,
            steps=step_results,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
        )
