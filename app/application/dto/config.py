"""Transport-independent configuration transfer objects."""

from dataclasses import dataclass
from datetime import datetime

from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.types import JsonObject
from app.core.types import NodeName, TagList

CONFIG_FORMAT_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class NodeConfigDTO:
    name: NodeName
    endpoint: NodeEndpoint
    credentials: NodeCredentials = NodeCredentials()
    tags: TagList = ()

    @property
    def host(self) -> str:
        return self.endpoint.host

    @property
    def port(self) -> int:
        return self.endpoint.port

    @property
    def connection_type(self) -> str:
        return self.endpoint.connection_type

    @property
    def docker_host(self) -> str | None:
        return self.endpoint.docker_host

    @property
    def username(self) -> str | None:
        return self.credentials.username


@dataclass(frozen=True, slots=True)
class CommandConfigDTO:
    name: NodeName
    command: str
    description: str | None = None
    parameters: tuple[JsonObject, ...] = ()
    tags: TagList = ()


@dataclass(frozen=True, slots=True)
class ScriptConfigDTO:
    name: NodeName
    description: str | None = None
    steps: tuple[JsonObject, ...] = ()
    tags: TagList = ()


@dataclass(frozen=True, slots=True)
class ConfigTransferDTO:
    nodes: tuple[NodeConfigDTO, ...] = ()
    commands: tuple[CommandConfigDTO, ...] = ()
    scripts: tuple[ScriptConfigDTO, ...] = ()
    format_version: str | None = None
    application_version: str | None = None
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
