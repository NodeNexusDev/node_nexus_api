"""Transport-independent configuration transfer objects."""

from dataclasses import dataclass
from datetime import datetime

from app.application.types import JsonObject

CONFIG_FORMAT_VERSION = "1.0"
LEGACY_CONFIG_VERSION = "0.5.0"


@dataclass(frozen=True, slots=True)
class NodeConfigDTO:
    name: str
    host: str
    port: int
    connection_type: str
    username: str | None = None
    docker_host: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandConfigDTO:
    name: str
    command: str
    description: str | None = None
    parameters: tuple[JsonObject, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScriptConfigDTO:
    name: str
    description: str | None = None
    steps: tuple[JsonObject, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfigTransferDTO:
    nodes: tuple[NodeConfigDTO, ...] = ()
    commands: tuple[CommandConfigDTO, ...] = ()
    scripts: tuple[ScriptConfigDTO, ...] = ()
    format_version: str | None = None
    application_version: str | None = None
    legacy_version: str | None = None
    exported_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConfigImportResultDTO:
    nodes_created: int = 0
    commands_created: int = 0
    scripts_created: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DryRunPreviewDTO:
    """Preview of what a dry-run import would do without writing."""

    would_create_nodes: tuple[NodeConfigDTO, ...] = ()
    would_create_commands: tuple[CommandConfigDTO, ...] = ()
    would_create_scripts: tuple[ScriptConfigDTO, ...] = ()
    duplicates: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
