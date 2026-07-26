"""Config service for export/import operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.repositories.command_repo import CommandRepository
    from app.repositories.node_repo import NodeRepository
    from app.repositories.script_repo import ScriptRepository

from app.schemas.config import (
    CommandExport,
    ConfigExport,
    ConfigImport,
    ImportResult,
    NodeExport,
    ScriptExport,
)


class ConfigService:
    """Service for exporting and importing node/command/script configurations."""

    def __init__(
        self,
        node_repository: NodeRepository,
        command_repository: CommandRepository,
        script_repository: ScriptRepository,
    ):
        self._node_repo = node_repository
        self._command_repo = command_repository
        self._script_repo = script_repository

    async def export_all(self) -> ConfigExport:
        """Export all nodes, commands, and scripts."""
        nodes = await self._node_repo.get_all(skip=0, limit=10000)
        commands = await self._command_repo.get_all(skip=0, limit=10000)
        scripts = await self._script_repo.get_all(skip=0, limit=10000)

        return ConfigExport(
            exported_at=datetime.now(UTC),
            nodes=[
                NodeExport(
                    name=n.name,
                    host=n.host,
                    port=n.port,
                    connection_type=n.connection_type,
                    username=n.username,
                    tags=n.tags or [],
                )
                for n in nodes
            ],
            commands=[
                CommandExport(
                    name=c.name,
                    description=c.description,
                    command=c.command,
                    parameters=c.parameters,
                    tags=c.tags or [],
                )
                for c in commands
            ],
            scripts=[
                ScriptExport(
                    name=s.name,
                    description=s.description,
                    steps=s.steps or [],
                    tags=s.tags or [],
                )
                for s in scripts
            ],
        )

    async def import_config(self, data: ConfigImport) -> ImportResult:
        """Import configuration. Skips duplicates by name."""
        result = ImportResult()

        for node_data in data.nodes:
            existing = await self._node_repo.get_all(skip=0, limit=10000)
            if any(n.name == node_data.name for n in existing):
                result.errors.append(f"Node '{node_data.name}' already exists, skipped")
                continue
            await self._node_repo.create(node_data.model_dump())
            result.nodes_created += 1

        for cmd_data in data.commands:
            existing = await self._command_repo.get_all(skip=0, limit=10000)
            if any(c.name == cmd_data.name for c in existing):
                result.errors.append(
                    f"Command '{cmd_data.name}' already exists, skipped"
                )
                continue
            await self._command_repo.create(cmd_data.model_dump())
            result.commands_created += 1

        for script_data in data.scripts:
            existing = await self._script_repo.get_all(skip=0, limit=10000)
            if any(s.name == script_data.name for s in existing):
                result.errors.append(
                    f"Script '{script_data.name}' already exists, skipped"
                )
                continue
            await self._script_repo.create(script_data.model_dump())
            result.scripts_created += 1

        return result
