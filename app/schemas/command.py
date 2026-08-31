"""Command schemas for API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import JsonObject, JsonValue


class CommandParameter(BaseModel):
    """Definition of a single command parameter."""

    name: str = Field(..., min_length=1, max_length=100)
    type: Literal["string", "integer", "boolean"] = Field(default="string")
    required: bool = Field(default=True)
    default: JsonValue = Field(default=None)
    description: str | None = Field(default=None, max_length=500)


class CommandCreate(BaseModel):
    """Schema for creating a command template."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    command: str = Field(..., min_length=1, max_length=4096)
    parameters: list[CommandParameter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CommandUpdate(BaseModel):
    """Schema for updating a command template."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    command: str | None = Field(default=None, min_length=1, max_length=4096)
    parameters: list[CommandParameter] | None = None
    tags: list[str] | None = None


class CommandResponse(BaseModel):
    """Schema for command response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    command: str
    parameters: list[CommandParameter] | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class CommandExecuteRequest(BaseModel):
    """Request to execute a command on a node."""

    node_id: uuid.UUID
    params: JsonObject = Field(default_factory=dict)


class CommandResult(BaseModel):
    """Result of a single command execution."""

    stdout: str
    stderr: str
    exit_code: int


class CommandBulkCreateRequest(BaseModel):
    """Bulk create commands (1..20)."""

    items: list[CommandCreate] = Field(min_length=1, max_length=20)


class CommandBulkCreateResult(BaseModel):
    """Result of creating a single command."""

    id: uuid.UUID | None = None
    name: str | None = None
    status: Literal["success", "error"]
    error: str = ""


class CommandExecutionsRequest(BaseModel):
    """M×N command executions (command_ids × nodes)."""

    command_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    params: dict[str, JsonObject] = Field(default_factory=dict)

    @property
    def _estimated_n(self) -> int:
        # best-effort M*N check without resolving tags
        n = len(self.node_ids) if self.node_ids else (len(self.node_tags) or 1)
        return len(self.command_ids) * n


class RawExecutionsRequest(BaseModel):
    """Bulk raw command executions."""

    commands: list[str] = Field(min_length=1, max_length=20)
    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)


class BulkExecutionItem(BaseModel):
    """Result of a single command execution on a single node."""

    command_id: uuid.UUID | None = None
    command: str | None = None
    node_id: uuid.UUID | None = None
    node_name: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    status: Literal["success", "error"]
    error: str = ""


class BulkExecutionBatchResponse(BaseModel):
    """Batch response for M×N executions."""

    batch_id: uuid.UUID
    total: int
    succeeded: int
    failed: int
    results: list[BulkExecutionItem]


class ExecutionRetriesRequest(BaseModel):
    """Request to retry multiple executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ExecutionCancelsRequest(BaseModel):
    """Request to cancel multiple executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
