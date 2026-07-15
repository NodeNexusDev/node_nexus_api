"""Node schemas for API."""

import uuid
from datetime import datetime
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

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
    tags: list[str] = Field(default_factory=list)


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
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class CommandRequest(BaseModel):
    """Schema for executing a command on a node."""

    command: str = Field(min_length=1, max_length=4096)


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
