"""Script schemas for API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScriptStep(BaseModel):
    """Definition of a single step in a script."""

    label: str = Field(..., min_length=1, max_length=255)
    type: Literal["inline", "command"]
    command: str | None = Field(default=None, max_length=4096)
    command_id: uuid.UUID | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    on_failure: Literal["stop", "continue"] = Field(default="stop")


class ScriptCreate(BaseModel):
    """Schema for creating a script."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    steps: list[ScriptStep] = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)


class ScriptUpdate(BaseModel):
    """Schema for updating a script."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    steps: list[ScriptStep] | None = Field(default=None, min_length=1)
    tags: list[str] | None = None


class ScriptResponse(BaseModel):
    """Schema for script response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    steps: list[ScriptStep]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class ScriptExecuteRequest(BaseModel):
    """Request to execute a script on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class ScriptStepResult(BaseModel):
    """Result of a single step in a script execution."""

    step_index: int
    label: str
    command_fingerprint: str
    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool = False
    exit_code: int


class ScriptNodeResult(BaseModel):
    """Result of a script execution on one node."""

    execution_id: uuid.UUID
    node_id: uuid.UUID
    node_name: str
    status: str
    steps: list[ScriptStepResult]


class ScriptExecutionBatchResult(BaseModel):
    """Batch result of script execution across multiple nodes."""

    script_id: uuid.UUID
    results: list[ScriptNodeResult]
