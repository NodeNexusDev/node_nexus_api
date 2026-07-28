"""Persistence ports for long-running script execution."""

from typing import Any, Protocol
from uuid import UUID

from app.application.dto.script_definition import ScriptDefinitionDTO


class ScriptDefinitionReader(Protocol):
    """Read immutable script definitions in a short scope."""

    async def get_definition(self, script_id: UUID) -> ScriptDefinitionDTO | None:
        """Return one script definition."""
        ...


class ScriptExecutionWriter(Protocol):
    """Persist execution state using independent short transactions."""

    async def create_execution(self, data: dict[str, Any]) -> UUID:
        """Create an execution and return its identifier."""
        ...

    async def update_execution(self, execution_id: UUID, data: dict[str, Any]) -> None:
        """Update and commit execution state."""
        ...
