"""Node schemas for API."""

import uuid
from datetime import datetime
from typing import Literal, TypeVar

import structlog
from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")

ConnectionType = Literal["ssh", "docker", "proxmox"]
NodeStatus = Literal["active", "unreachable", "error"]


class PaginatedResponse[T](BaseModel):
    """Paginated response with total count."""

    items: list[T]
    total: int
    page: int
    size: int


class NodeCreate(BaseModel):
    """Schema for creating a node."""

    name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    connection_type: ConnectionType
    username: str | None = None
    password: str | None = None
    ssh_key: str | None = None
    docker_host: str | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_docker_host(self) -> "NodeCreate":
        if self.connection_type == "docker" and not self.docker_host:
            structlog.get_logger("validation").warning(
                "docker_host_not_set",
                connection_type=self.connection_type,
                host=self.host,
            )
        return self


class NodeUpdate(BaseModel):
    """Schema for updating a node."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    connection_type: ConnectionType | None = None
    status: NodeStatus | None = None
    username: str | None = None
    password: str | None = None
    ssh_key: str | None = None
    docker_host: str | None = None
    tags: list[str] | None = None


class NodeResponse(BaseModel):
    """Schema for node response. Never includes secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    host: str
    port: int
    connection_type: str
    status: str
    username: str | None
    docker_host: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class CommandRequest(BaseModel):
    """Schema for executing a command on a node."""

    command: str = Field(min_length=1, max_length=4096)
    timeout: int | None = Field(default=None, ge=1, le=600)


class CommandResult(BaseModel):
    """Schema for command execution result."""

    stdout: str
    stderr: str
    exit_code: int


class TagAdd(BaseModel):
    """Schema for adding a tag to a node."""

    tag: str = Field(min_length=1, max_length=100)


class TagRemove(BaseModel):
    """Schema for removing a tag from a node."""

    tag: str = Field(min_length=1, max_length=100)


class BulkCommandRequest(BaseModel):
    """Request to execute a command on multiple nodes."""

    command: str = Field(min_length=1, max_length=4096)
    node_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    tags: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def check_targets(self) -> "BulkCommandRequest":
        if not self.node_ids and not self.tags:
            raise ValueError("At least one of node_ids or tags must be provided")
        return self


class BulkNodeResult(BaseModel):
    """Result of command execution on a single node."""

    node_id: uuid.UUID
    node_name: str
    stdout: str
    stderr: str
    exit_code: int


class BulkCommandResult(BaseModel):
    """Result of bulk command execution across multiple nodes."""

    command: str
    results: list[BulkNodeResult]
    total: int
    succeeded: int
    failed: int


class CommandHistoryResponse(BaseModel):
    """One command execution record in a node's history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command_fingerprint: str
    exit_code: int
    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


class CpuMetrics(BaseModel):
    """CPU metrics from a node."""

    usage_percent: float = Field(ge=0, le=100)
    cores: int = Field(ge=1)


class MemoryMetrics(BaseModel):
    """Memory metrics from a node."""

    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)


class DiskMetrics(BaseModel):
    """Disk metrics from a node."""

    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)


class NodeMetrics(BaseModel):
    """System metrics from a node."""

    cpu: CpuMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    uptime_since: str
