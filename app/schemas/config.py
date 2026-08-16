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
    dry_run: bool = False
    nodes: list[NodeExport] = Field(default_factory=list)
    commands: list[CommandExport] = Field(default_factory=list)
    scripts: list[ScriptExport] = Field(default_factory=list)


class ImportResult(BaseModel):
    """Result of a configuration import."""

    nodes_created: int = 0
    commands_created: int = 0
    scripts_created: int = 0
    errors: list[str] = Field(default_factory=list)


class DryRunNodePreview(BaseModel):
    """Preview of a node that would be created."""

    name: str
    host: str
    port: int
    connection_type: str
    username: str | None = None
    tags: list[str] = Field(default_factory=list)


class DryRunCommandPreview(BaseModel):
    """Preview of a command that would be created."""

    name: str
    description: str | None = None
    command: str
    tags: list[str] = Field(default_factory=list)


class DryRunScriptPreview(BaseModel):
    """Preview of a script that would be created."""

    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class DryRunWouldCreate(BaseModel):
    """Summary of items that would be created."""

    nodes: list[DryRunNodePreview] = Field(default_factory=list)
    commands: list[DryRunCommandPreview] = Field(default_factory=list)
    scripts: list[DryRunScriptPreview] = Field(default_factory=list)


class DryRunImportResult(BaseModel):
    """Result of a dry-run configuration import."""

    dry_run: bool = True
    would_create: DryRunWouldCreate = Field(default_factory=DryRunWouldCreate)
    duplicates: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
