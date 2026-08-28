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
