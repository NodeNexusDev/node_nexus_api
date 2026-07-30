"""Schemas for configuration export/import."""

from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel, Field

from app.application.dto.config import CONFIG_FORMAT_VERSION, LEGACY_CONFIG_VERSION


def application_version() -> str:
    """Return the installed application package version."""
    try:
        return version("node-nexus-api")
    except PackageNotFoundError:
        return "unknown"


class NodeExport(BaseModel):
    """Exported node configuration (secrets excluded)."""

    name: str
    host: str
    port: int
    connection_type: str
    username: str | None = None
    tags: list[str] = Field(default_factory=list)


class CommandExport(BaseModel):
    """Exported command template."""

    name: str
    description: str | None = None
    command: str
    parameters: list[dict] | None = None
    tags: list[str] = Field(default_factory=list)


class ScriptExport(BaseModel):
    """Exported script configuration."""

    name: str
    description: str | None = None
    steps: list[dict] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ConfigExport(BaseModel):
    """Full configuration export."""

    format_version: str = CONFIG_FORMAT_VERSION
    application_version: str = Field(default_factory=application_version)
    version: str = LEGACY_CONFIG_VERSION
    exported_at: datetime
    nodes: list[NodeExport] = Field(default_factory=list)
    commands: list[CommandExport] = Field(default_factory=list)
    scripts: list[ScriptExport] = Field(default_factory=list)


class ConfigImport(BaseModel):
    """Configuration import payload."""

    format_version: str | None = None
    application_version: str | None = None
    version: str | None = None
    nodes: list[NodeExport] = Field(default_factory=list)
    commands: list[CommandExport] = Field(default_factory=list)
    scripts: list[ScriptExport] = Field(default_factory=list)


class ImportResult(BaseModel):
    """Result of a configuration import."""

    nodes_created: int = 0
    commands_created: int = 0
    scripts_created: int = 0
    errors: list[str] = Field(default_factory=list)
