"""Short-scope SQLAlchemy adapters for script execution."""

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
from app.application.types import PersistenceObject
from app.core.types import JsonObject
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

    async def create_execution(self, data: PersistenceObject) -> UUID:
        async with self._sessionmaker.begin() as session:
            execution = await ScriptExecutionRepository(session).create(data)
            return execution.id

    async def update_execution(
        self, execution_id: UUID, data: PersistenceObject
    ) -> None:
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
            if not all(isinstance(step, ScriptStepDTO) for step in steps):
                raise TypeError("Script update contains an invalid step")
            changes["steps"] = [self._step_to_dict(step) for step in steps]
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
    def _step_from_dict(step: JsonObject) -> ScriptStepDTO:
        label = _required_str(step, "label")
        step_type = _required_str(step, "type")
        if step_type not in ("inline", "command"):
            raise ValueError("Stored script step type is invalid")
        command = _optional_str(step, "command")
        command_id_value = _optional_str(step, "command_id")
        params_value = step.get("params", {})
        if not isinstance(params_value, dict):
            raise ValueError("Stored script step params must be an object")
        failure_policy = _required_str(step, "on_failure", default="stop")
        if failure_policy not in ("stop", "continue"):
            raise ValueError("Stored script failure policy is invalid")
        return ScriptStepDTO(
            label=label,
            type=step_type,
            command=command,
            command_id=UUID(command_id_value) if command_id_value else None,
            params=tuple(params_value.items()),
            on_failure=failure_policy,
        )

    @staticmethod
    def _step_to_dict(step: ScriptStepDTO) -> JsonObject:
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
            _step_result_from_dict(step) for step in (execution.steps or ())
        )
        if execution.status not in (
            "pending",
            "running",
            "success",
            "error",
            "cancelled",
        ):
            raise ValueError("Stored script execution status is invalid")
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


def _required_str(data: JsonObject, key: str, *, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Stored field {key!r} must be a string")
    return value


def _optional_str(data: JsonObject, key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Stored field {key!r} must be a string or null")
    return value


def _required_int(data: JsonObject, key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Stored field {key!r} must be an integer")
    return value


def _required_bool(data: JsonObject, key: str, *, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Stored field {key!r} must be a boolean")
    return value


def _step_result_from_dict(step: JsonObject) -> ScriptStepResultDTO:
    return ScriptStepResultDTO(
        step_index=_required_int(step, "step_index"),
        label=_required_str(step, "label"),
        command_fingerprint=_required_str(step, "command_fingerprint"),
        stdout=_required_str(step, "stdout"),
        stderr=_required_str(step, "stderr"),
        stdout_bytes=_required_int(step, "stdout_bytes"),
        stderr_bytes=_required_int(step, "stderr_bytes"),
        truncated=_required_bool(step, "truncated"),
        exit_code=_required_int(step, "exit_code"),
    )
