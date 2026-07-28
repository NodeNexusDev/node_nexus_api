"""Config service for export/import operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

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

    @staticmethod
    async def _load_all(repository: Any, batch_size: int = 1000) -> list[Any]:
        """Load an unbounded collection through the repository pagination API."""
        items: list[Any] = []
        while True:
            batch = await repository.get_all(skip=len(items), limit=batch_size)
            items.extend(batch)
            if len(batch) < batch_size:
                return items

    async def export_all(self) -> ConfigExport:
        """Export all nodes, commands, and scripts."""
        nodes = await self._load_all(self._node_repo)
        commands = await self._load_all(self._command_repo)
        scripts = await self._load_all(self._script_repo)

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
        """Import configuration atomically, skipping duplicate names."""
        result = ImportResult()
        existing_node_names = {
            item.name
            for item in (await self._load_all(self._node_repo) if data.nodes else [])
        }
        existing_command_names = {
            item.name
            for item in (
                await self._load_all(self._command_repo) if data.commands else []
            )
        }
        existing_script_names = {
            item.name
            for item in (
                await self._load_all(self._script_repo) if data.scripts else []
            )
        }

        for node_data in data.nodes:
            if node_data.name in existing_node_names:
                result.errors.append(f"Node '{node_data.name}' already exists, skipped")
                continue
            await self._node_repo.create(node_data.model_dump())
            existing_node_names.add(node_data.name)
            result.nodes_created += 1

        for cmd_data in data.commands:
            if cmd_data.name in existing_command_names:
                result.errors.append(
                    f"Command '{cmd_data.name}' already exists, skipped"
                )
                continue
            await self._command_repo.create(cmd_data.model_dump())
            existing_command_names.add(cmd_data.name)
            result.commands_created += 1

        for script_data in data.scripts:
            if script_data.name in existing_script_names:
                result.errors.append(
                    f"Script '{script_data.name}' already exists, skipped"
                )
                continue
            await self._script_repo.create(script_data.model_dump())
            existing_script_names.add(script_data.name)
            result.scripts_created += 1

        return result
