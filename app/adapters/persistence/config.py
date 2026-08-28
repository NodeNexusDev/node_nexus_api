"""SQLAlchemy adapter for coordinated configuration transfer."""

from collections.abc import Sequence
from typing import Protocol, TypeVar, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.command import CommandRepository
from app.adapters.persistence.dao.node import NodeRepository
from app.adapters.persistence.dao.script import ScriptRepository
from app.application.dto.config import (
    CommandConfigDTO,
    ConfigImportResultDTO,
    ConfigTransferDTO,
    DryRunPreviewDTO,
    NodeConfigDTO,
    ScriptConfigDTO,
)
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.core.types import ConnectionType

RecordT = TypeVar("RecordT")


class _PagedReader(Protocol[RecordT]):
    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[RecordT]: ...


class SqlAlchemyConfigGateway:
    """Export and atomically import configuration using one persistence boundary."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        batch_size: int = 1000,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._batch_size = batch_size

    async def _load_all(self, reader: _PagedReader[RecordT]) -> list[RecordT]:
        items: list[RecordT] = []
        while True:
            batch = await reader.get_all(
                skip=len(items),
                limit=self._batch_size,
            )
            items.extend(batch)
            if len(batch) < self._batch_size:
                return items

    async def export_config(self) -> ConfigTransferDTO:
        """Read a complete snapshot in bounded pages."""
        async with self._sessionmaker() as session:
            nodes = await self._load_all(NodeRepository(session))
            commands = await self._load_all(CommandRepository(session))
            scripts = await self._load_all(ScriptRepository(session))

        return ConfigTransferDTO(
            nodes=tuple(
                NodeConfigDTO(
                    name=node.name,
                    endpoint=NodeEndpoint(
                        host=node.host,
                        port=node.port,
                        connection_type=cast(ConnectionType, node.connection_type),
                        docker_host=node.docker_host,
                    ),
                    credentials=NodeCredentials(username=node.username),
                    tags=tuple(node.tags or ()),
                )
                for node in nodes
            ),
            commands=tuple(
                CommandConfigDTO(
                    name=command.name,
                    description=command.description,
                    command=command.command,
                    parameters=tuple(command.parameters or ()),
                    tags=tuple(command.tags or ()),
                )
                for command in commands
            ),
            scripts=tuple(
                ScriptConfigDTO(
                    name=script.name,
                    description=script.description,
                    steps=tuple(script.steps or ()),
                    tags=tuple(script.tags or ()),
                )
                for script in scripts
            ),
        )

    async def import_config(self, data: ConfigTransferDTO) -> ConfigImportResultDTO:
        """Import all entity types within one SQLAlchemy transaction."""
        errors: list[str] = []
        nodes_created = commands_created = scripts_created = 0

        async with self._sessionmaker.begin() as session:
            node_repository = NodeRepository(session)
            command_repository = CommandRepository(session)
            script_repository = ScriptRepository(session)

            existing_node_names = {
                item.name
                for item in (
                    await self._load_all(node_repository) if data.nodes else ()
                )
            }
            existing_command_names = {
                item.name
                for item in (
                    await self._load_all(command_repository) if data.commands else ()
                )
            }
            existing_script_names = {
                item.name
                for item in (
                    await self._load_all(script_repository) if data.scripts else ()
                )
            }

            for node in data.nodes:
                if node.name in existing_node_names:
                    errors.append(f"Node '{node.name}' already exists, skipped")
                    continue
                await node_repository.create(
                    {
                        "name": node.name,
                        "host": node.endpoint.host,
                        "port": node.endpoint.port,
                        "connection_type": node.endpoint.connection_type,
                        "username": node.credentials.username,
                        "docker_host": node.endpoint.docker_host,
                        "tags": list(node.tags),
                    }
                )
                existing_node_names.add(node.name)
                nodes_created += 1

            for command in data.commands:
                if command.name in existing_command_names:
                    errors.append(f"Command '{command.name}' already exists, skipped")
                    continue
                await command_repository.create(
                    {
                        "name": command.name,
                        "description": command.description,
                        "command": command.command,
                        "parameters": list(command.parameters),
                        "tags": list(command.tags),
                    }
                )
                existing_command_names.add(command.name)
                commands_created += 1

            for script in data.scripts:
                if script.name in existing_script_names:
                    errors.append(f"Script '{script.name}' already exists, skipped")
                    continue
                await script_repository.create(
                    {
                        "name": script.name,
                        "description": script.description,
                        "steps": list(script.steps),
                        "tags": list(script.tags),
                    }
                )
                existing_script_names.add(script.name)
                scripts_created += 1

        return ConfigImportResultDTO(
            nodes_created=nodes_created,
            commands_created=commands_created,
            scripts_created=scripts_created,
            errors=tuple(errors),
        )

    async def preview_import(self, data: ConfigTransferDTO) -> DryRunPreviewDTO:
        """Preview what an import would do without writing to the database."""
        would_create_nodes: list[NodeConfigDTO] = []
        would_create_commands: list[CommandConfigDTO] = []
        would_create_scripts: list[ScriptConfigDTO] = []
        duplicates: list[str] = []
        errors: list[str] = []

        async with self._sessionmaker() as session:
            node_repository = NodeRepository(session)
            command_repository = CommandRepository(session)
            script_repository = ScriptRepository(session)

            existing_node_names = {
                item.name
                for item in (
                    await self._load_all(node_repository) if data.nodes else ()
                )
            }
            existing_command_names = {
                item.name
                for item in (
                    await self._load_all(command_repository) if data.commands else ()
                )
            }
            existing_script_names = {
                item.name
                for item in (
                    await self._load_all(script_repository) if data.scripts else ()
                )
            }

            for node in data.nodes:
                if node.name in existing_node_names:
                    duplicates.append(f"Node '{node.name}' already exists")
                else:
                    would_create_nodes.append(node)

            for command in data.commands:
                if command.name in existing_command_names:
                    duplicates.append(f"Command '{command.name}' already exists")
                else:
                    would_create_commands.append(command)

            for script in data.scripts:
                if script.name in existing_script_names:
                    duplicates.append(f"Script '{script.name}' already exists")
                else:
                    would_create_scripts.append(script)

        return DryRunPreviewDTO(
            would_create_nodes=tuple(would_create_nodes),
            would_create_commands=tuple(would_create_commands),
            would_create_scripts=tuple(would_create_scripts),
            duplicates=tuple(duplicates),
            errors=tuple(errors),
        )
