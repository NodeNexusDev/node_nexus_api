"""Command schemas for API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CommandParameter(BaseModel):
    """Definition of a single command parameter."""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(default="string", pattern=r"^(string|integer|boolean)$")
    required: bool = Field(default=True)
    default: Any = Field(default=None)
    description: str | None = Field(default=None, max_length=500)


class CommandCreate(BaseModel):
    """Schema for creating a command template."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    command: str = Field(..., min_length=1, max_length=4096)
    parameters: list[CommandParameter] = Field(default_factory=list)


class CommandUpdate(BaseModel):
    """Schema for updating a command template."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    command: str | None = Field(default=None, min_length=1, max_length=4096)
    parameters: list[CommandParameter] | None = None


class CommandResponse(BaseModel):
    """Schema for command response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    command: str
    parameters: list[CommandParameter] | None
    created_at: datetime
    updated_at: datetime


class CommandExecuteRequest(BaseModel):
    """Request to execute a command on a node."""

    node_id: uuid.UUID
    params: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    """Result of a single command execution."""

    stdout: str
    stderr: str
    exit_code: int
