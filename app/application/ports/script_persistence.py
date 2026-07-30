"""Persistence ports for long-running script execution."""

from typing import Protocol
from uuid import UUID

from app.application.dto.script_definition import ScriptDefinitionDTO
from app.application.dto.script_execution import (
    ScriptExecutionPageDTO,
    ScriptExecutionQueryDTO,
)
from app.application.dto.script_management import (
    ScriptCreateDTO,
    ScriptListQueryDTO,
    ScriptPageDTO,
    ScriptUpdateDTO,
    ScriptViewDTO,
)
from app.application.types import PersistenceObject


class ScriptReader(Protocol):
    """Read script management views."""

    async def get_script(self, script_id: UUID) -> ScriptViewDTO | None:
        """Return one script."""
        ...

    async def list_scripts(self, query: ScriptListQueryDTO) -> ScriptPageDTO:
        """Return one page of scripts."""
        ...


class ScriptWriter(Protocol):
    """Persist script mutations."""

    async def create_script(self, data: ScriptCreateDTO) -> ScriptViewDTO:
        """Create and return a script."""
        ...

    async def update_script(
        self, script_id: UUID, data: ScriptUpdateDTO
    ) -> ScriptViewDTO | None:
        """Update and return a script when it exists."""
        ...

    async def delete_script(self, script_id: UUID) -> bool:
        """Delete a script and report whether it existed."""
        ...


class ScriptExecutionReader(Protocol):
    """Read immutable execution history."""

    async def list_executions(
        self, query: ScriptExecutionQueryDTO
    ) -> ScriptExecutionPageDTO:
        """Return one page of execution history."""
        ...


class ScriptDefinitionReader(Protocol):
    """Read immutable script definitions in a short scope."""

    async def get_definition(self, script_id: UUID) -> ScriptDefinitionDTO | None:
        """Return one script definition."""
        ...


class ScriptExecutionWriter(Protocol):
    """Persist execution state using independent short transactions."""

    async def create_execution(self, data: PersistenceObject) -> UUID:
        """Create an execution and return its identifier."""
        ...

    async def update_execution(
        self, execution_id: UUID, data: PersistenceObject
    ) -> None:
        """Update and commit execution state."""
        ...
