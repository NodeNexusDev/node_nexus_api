"""Configuration export and import application use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import TypeVar, cast

from app.application.dto.config import (
    CONFIG_FORMAT_VERSION,
    LEGACY_CONFIG_VERSION,
    CommandConfigDTO,
    ConfigImportResultDTO,
    ConfigTransferDTO,
    NodeConfigDTO,
    ScriptConfigDTO,
)
from app.application.ports.config_persistence import (
    CommandConfigStore,
    ConfigRecordReader,
    NodeConfigStore,
    ScriptConfigStore,
)
from app.application.types import PersistenceObject
from app.core.exceptions import UnsupportedConfigFormatError

RecordT = TypeVar("RecordT")


class ConfigService:
    """Service for exporting and importing node/command/script configurations."""

    def __init__(
        self,
        node_repository: NodeConfigStore,
        command_repository: CommandConfigStore,
        script_repository: ScriptConfigStore,
    ):
        self._node_repo = node_repository
        self._command_repo = command_repository
        self._script_repo = script_repository

    @staticmethod
    async def _load_all(
        repository: ConfigRecordReader[RecordT], batch_size: int = 1000
    ) -> list[RecordT]:
        """Load an unbounded collection through the repository pagination API."""
        items: list[RecordT] = []
        while True:
            batch = await repository.get_all(skip=len(items), limit=batch_size)
            items.extend(batch)
            if len(batch) < batch_size:
                return items

    async def export_all(self) -> ConfigTransferDTO:
        """Export all nodes, commands, and scripts."""
        nodes = await self._load_all(self._node_repo)
        commands = await self._load_all(self._command_repo)
        scripts = await self._load_all(self._script_repo)

        return ConfigTransferDTO(
            format_version=CONFIG_FORMAT_VERSION,
            application_version=_application_version(),
            legacy_version=LEGACY_CONFIG_VERSION,
            exported_at=datetime.now(UTC),
            nodes=tuple(
                NodeConfigDTO(
                    name=n.name,
                    host=n.host,
                    port=n.port,
                    connection_type=n.connection_type,
                    username=n.username,
                    tags=tuple(n.tags or ()),
                )
                for n in nodes
            ),
            commands=tuple(
                CommandConfigDTO(
                    name=c.name,
                    description=c.description,
                    command=c.command,
                    parameters=tuple(c.parameters or ()),
                    tags=tuple(c.tags or ()),
                )
                for c in commands
            ),
            scripts=tuple(
                ScriptConfigDTO(
                    name=s.name,
                    description=s.description,
                    steps=tuple(s.steps or ()),
                    tags=tuple(s.tags or ()),
                )
                for s in scripts
            ),
        )

    async def import_config(self, data: ConfigTransferDTO) -> ConfigImportResultDTO:
        """Import configuration atomically, skipping duplicate names."""
        if data.format_version is not None:
            received_major = data.format_version.split(".", maxsplit=1)[0]
            supported_major = CONFIG_FORMAT_VERSION.split(".", maxsplit=1)[0]
            if received_major != supported_major:
                raise UnsupportedConfigFormatError(
                    "Unsupported configuration format "
                    f"{data.format_version}; supported major is {supported_major}"
                )
        nodes_created = commands_created = scripts_created = 0
        errors: list[str] = []
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
                errors.append(f"Node '{node_data.name}' already exists, skipped")
                continue
            await self._node_repo.create(
                {
                    "name": node_data.name,
                    "host": node_data.host,
                    "port": node_data.port,
                    "connection_type": node_data.connection_type,
                    "username": node_data.username,
                    "tags": list(node_data.tags),
                }
            )
            existing_node_names.add(node_data.name)
            nodes_created += 1

        for cmd_data in data.commands:
            if cmd_data.name in existing_command_names:
                errors.append(f"Command '{cmd_data.name}' already exists, skipped")
                continue
            await self._command_repo.create(
                cast(
                    PersistenceObject,
                    {
                        "name": cmd_data.name,
                        "description": cmd_data.description,
                        "command": cmd_data.command,
                        "parameters": list(cmd_data.parameters or ()),
                        "tags": list(cmd_data.tags),
                    },
                )
            )
            existing_command_names.add(cmd_data.name)
            commands_created += 1

        for script_data in data.scripts:
            if script_data.name in existing_script_names:
                errors.append(f"Script '{script_data.name}' already exists, skipped")
                continue
            await self._script_repo.create(
                cast(
                    PersistenceObject,
                    {
                        "name": script_data.name,
                        "description": script_data.description,
                        "steps": list(script_data.steps),
                        "tags": list(script_data.tags),
                    },
                )
            )
            existing_script_names.add(script_data.name)
            scripts_created += 1

        return ConfigImportResultDTO(
            nodes_created=nodes_created,
            commands_created=commands_created,
            scripts_created=scripts_created,
            errors=tuple(errors),
        )


def _application_version() -> str:
    try:
        return version("node-nexus-api")
    except PackageNotFoundError:
        return "unknown"
