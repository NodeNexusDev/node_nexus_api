# ruff: noqa: F401, I001
"""Node schemas — command."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.docker_validation import validate_docker_host
from app.core.types import ConnectionType, JsonObject, NodeStatus
from app.schemas.common import CursorPage, PaginatedResponse


class CommandRequest(BaseModel):
    """Schema for executing a command on a node."""

    command: str = Field(min_length=1, max_length=4096)
    timeout: int | None = Field(default=None, ge=1, le=600)


class CommandExecuteRawRequest(BaseModel):
    """Schema for executing a raw command via the commands endpoint."""

    node_id: uuid.UUID
    command: str = Field(min_length=1, max_length=4096)
    timeout: int | None = Field(default=None, ge=1, le=600)


class BulkCommandRequest(BaseModel):
    """Request to execute a command on multiple nodes."""

    command: str = Field(min_length=1, max_length=4096)
    node_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    tags: list[str] | None = Field(default=None, min_length=1)
    params: JsonObject | None = Field(default=None)

    @model_validator(mode="after")
    def check_targets(self) -> Self:
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
