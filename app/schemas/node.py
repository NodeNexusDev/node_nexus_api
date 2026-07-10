"""Node schemas for API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NodeCreate(BaseModel):
    """Schema for creating a node."""

    name: str
    host: str
    port: int = 22
    connection_type: str
    username: str | None = None
    ssh_key: str | None = None


class NodeUpdate(BaseModel):
    """Schema for updating a node."""

    name: str | None = None
    host: str | None = None
    port: int | None = None
    connection_type: str | None = None
    status: str | None = None
    username: str | None = None
    ssh_key: str | None = None


class NodeResponse(BaseModel):
    """Schema for node response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    host: str
    port: int
    connection_type: str
    status: str
    username: str | None
    created_at: datetime
    updated_at: datetime


class CommandRequest(BaseModel):
    """Schema for executing a command on a node."""

    command: str


class CommandResult(BaseModel):
    """Schema for command execution result."""

    stdout: str
    stderr: str
    exit_code: int
