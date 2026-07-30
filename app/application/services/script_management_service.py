"""Script management application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.application.dto.script_management import (
    ScriptCreateDTO,
    ScriptListQueryDTO,
    ScriptUpdateDTO,
    ScriptViewDTO,
)
from app.application.types import JsonObject
from app.core.exceptions import ScriptNotFoundError

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.script_persistence import ScriptReader, ScriptWriter

audit = structlog.get_logger("audit")


class ScriptManagementService:
    """Manage scripts through application persistence ports."""

    def __init__(
        self,
        reader: ScriptReader,
        writer: ScriptWriter,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._audit = audit_service

    async def _log(self, action: str, details: JsonObject) -> None:
        if self._audit:
            await self._audit.log(action=action, details=details)

    async def get_script(self, script_id: UUID) -> ScriptViewDTO:
        script = await self._reader.get_script(script_id)
        if script is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")
        return script

    async def get_all_scripts(
        self, page: int = 1, size: int = 20, tags: list[str] | None = None
    ) -> tuple[list[ScriptViewDTO], int]:
        result = await self._reader.list_scripts(
            ScriptListQueryDTO(
                offset=(page - 1) * size,
                limit=size,
                tags=tuple(tags or ()),
            )
        )
        return list(result.items), result.total

    async def create_script(self, data: ScriptCreateDTO) -> ScriptViewDTO:
        script = await self._writer.create_script(data)
        audit.info("script.create.ok", script_id=str(script.id), name=data.name)
        await self._log("create", {"entity": "script", "name": data.name})
        return script

    async def update_script(
        self, script_id: UUID, data: ScriptUpdateDTO
    ) -> ScriptViewDTO:
        script = await self._writer.update_script(script_id, data)
        if script is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")
        audit.info("script.update.ok", script_id=str(script_id))
        await self._log("update", {"entity": "script", "id": str(script_id)})
        return script

    async def delete_script(self, script_id: UUID) -> bool:
        if await self._reader.get_script(script_id) is None:
            raise ScriptNotFoundError(f"Script {script_id} not found")
        await self._log("delete", {"entity": "script", "id": str(script_id)})
        await self._writer.delete_script(script_id)
        audit.info("script.delete.ok", script_id=str(script_id))
        return True
