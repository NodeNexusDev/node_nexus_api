"""Node schemas for API."""

import uuid
from datetime import datetime
from typing import Any, Literal, TypeVar

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
    passphrase: str | None = None
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
    passphrase: str | None = None
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


class CommandExecuteRawRequest(BaseModel):
    """Schema for executing a raw command via the commands endpoint."""

    node_id: uuid.UUID
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
    params: dict[str, Any] | None = Field(default=None)

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


class BulkCommandHistoryItem(BaseModel):
    """Single command execution record in a bulk batch history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
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


class BulkCommandHistoryResponse(PaginatedResponse[BulkCommandHistoryItem]):
    """Paginated response for bulk command batch history."""

    pass


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


class LoadAverage(BaseModel):
    """System load average over 1, 5, and 15 minutes."""

    one_min: float = Field(ge=0)
    five_min: float = Field(ge=0)
    fifteen_min: float = Field(ge=0)


class NodeMetrics(BaseModel):
    """System metrics from a node."""

    cpu: CpuMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    load_average: LoadAverage
    uptime_since: str


class NodeValidateRequest(BaseModel):
    """Request to validate SSH credentials without saving a node."""

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    connection_type: ConnectionType = "ssh"
    username: str | None = None
    password: str | None = None
    ssh_key: str | None = None
    passphrase: str | None = None


class NodeValidateResponse(BaseModel):
    """Result of credential validation."""

    status: NodeStatus
    message: str


# --- Node status history ---


class NodeStatusHistoryItem(BaseModel):
    """Single status change record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node_id: uuid.UUID | None = None
    old_status: str | None = None
    new_status: str
    source: str
    changed_at: datetime


class NodeStatusHistoryResponse(PaginatedResponse[NodeStatusHistoryItem]):
    """Paginated status history for a node."""

    pass


# --- Bulk node operations ---


class BulkNodeDeleteRequest(BaseModel):
    """Request to delete multiple nodes."""

    node_ids: list[uuid.UUID] = Field(min_length=1)


class BulkNodeTagRequest(BaseModel):
    """Request to add or remove tags on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(min_length=1)
    tags: list[str] = Field(min_length=1)


class BulkNodeCheckRequest(BaseModel):
    """Request to check connectivity on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(min_length=1)


class BulkNodeOperationResult(BaseModel):
    """Result of a bulk node operation."""

    affected: int
    node_ids: list[uuid.UUID]
    total: int | None = None
    succeeded: int | None = None
    failed: int | None = None
    errors: list[str] | None = None


class BulkNodeMetricsRequest(BaseModel):
    """Request to collect metrics from multiple nodes."""

    node_ids: list[uuid.UUID] = Field(min_length=1)


class BulkNodeMetricsResult(BaseModel):
    """Metrics result for a single node."""

    node_id: uuid.UUID
    node_name: str
    status: str  # "success" or "error"
    metrics: NodeMetrics | None = None
    error: str = ""


class BulkNodeMetricsResponse(BaseModel):
    """Response for bulk metrics collection."""

    results: list[BulkNodeMetricsResult]
    total: int
    succeeded: int
    failed: int


class BulkNodeUpdateRequest(BaseModel):
    """Request to update multiple nodes with the same changes."""

    node_ids: list[uuid.UUID] = Field(min_length=1)
    changes: NodeUpdate


class BulkNodeUpdateResult(BaseModel):
    """Result of updating a single node."""

    node_id: uuid.UUID
    status: str  # "success" or "error"
    error: str = ""


class BulkNodeUpdateResponse(BaseModel):
    """Response for bulk node update."""

    results: list[BulkNodeUpdateResult]
    total: int
    succeeded: int
    failed: int


class ExecutionRetryResponse(BaseModel):
    """Response for retry/cancel execution."""

    execution_id: str
    status: str
    message: str


# --- Bulk validate credentials ---


class BulkValidateCredentialsRequest(BaseModel):
    """Request to validate SSH credentials for multiple existing nodes."""

    node_ids: list[uuid.UUID] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class BulkValidateCredentialsResult(BaseModel):
    """Credential validation result for a single node."""

    node_id: uuid.UUID
    node_name: str
    status: str  # "success" or "error"
    message: str = ""


class BulkValidateCredentialsResponse(BaseModel):
    """Response for bulk credential validation."""

    results: list[BulkValidateCredentialsResult]
    total: int
    succeeded: int
    failed: int


# --- Bulk retry/cancel commands ---


class BulkRetryCommandRequest(BaseModel):
    """Request to retry multiple command executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1)


class BulkRetryCommandResult(BaseModel):
    """Result of retrying a single command execution."""

    execution_id: str
    status: str  # "retry_scheduled" or "error"
    message: str = ""


class BulkRetryCommandResponse(BaseModel):
    """Response for bulk command retry."""

    results: list[BulkRetryCommandResult]
    total: int
    succeeded: int
    failed: int


class BulkCancelCommandRequest(BaseModel):
    """Request to cancel multiple command executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1)


class BulkCancelCommandResult(BaseModel):
    """Result of cancelling a single command execution."""

    execution_id: str
    status: str  # "cancelled" or "error"
    message: str = ""


class BulkCancelCommandResponse(BaseModel):
    """Response for bulk command cancellation."""

    results: list[BulkCancelCommandResult]
    total: int
    succeeded: int
    failed: int
