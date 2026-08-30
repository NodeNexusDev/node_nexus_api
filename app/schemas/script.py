"""Script schemas for API."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.types import JsonObject


class ScriptStep(BaseModel):
    """Definition of a single step in a script."""

    label: str = Field(..., min_length=1, max_length=255)
    type: Literal["inline", "command"]
    command: str | None = Field(default=None, max_length=4096)
    command_id: uuid.UUID | None = None
    command_name: str | None = Field(default=None, max_length=255)
    params: JsonObject = Field(default_factory=dict)
    on_failure: Literal["stop", "continue"] = Field(default="stop")

    @model_validator(mode="after")
    def check_command_ref(self) -> Self:
        if self.type == "command" and not self.command_id and not self.command_name:
            raise ValueError("command step requires command_id or command_name")
        if self.command_id and self.command_name:
            raise ValueError("Provide only one of command_id or command_name")
        return self


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

    node_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    node_tags: list[str] | None = Field(default=None, min_length=1)
    params: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_targets(self) -> Self:
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class ScriptStepResult(BaseModel):
    """Result of a single step in a script execution."""

    step_index: int
    label: str
    command_fingerprint: str = ""
    stdout: str
    stderr: str
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    truncated: bool = False
    exit_code: int


class ScriptNodeResult(BaseModel):
    """Result of a script execution on one node."""

    execution_id: uuid.UUID
    node_id: uuid.UUID
    node_name: str
    status: Literal["success", "error"]
    steps: list[ScriptStepResult]


class ScriptExecutionBatchResult(BaseModel):
    """Batch result of script execution across multiple nodes."""

    script_id: uuid.UUID
    results: list[ScriptNodeResult]


# --- Bulk operation schemas ---


class ScriptBulkRetryRequest(BaseModel):
    """Request to retry multiple script executions."""

    execution_ids: list[uuid.UUID] = Field(..., min_length=1)


class ScriptBulkCancelRequest(BaseModel):
    """Request to cancel multiple running script executions."""

    execution_ids: list[uuid.UUID] = Field(..., min_length=1)


class ScriptBulkResult(BaseModel):
    """Result of a single bulk operation item."""

    execution_id: str
    status: str
    message: str


class ScriptBulkOperationResponse(BaseModel):
    """Response for bulk script retry/cancel operations."""

    results: list[ScriptBulkResult]
    total: int
    succeeded: int
    failed: int


class ScriptRetryResponse(BaseModel):
    """Response for script retry operation."""

    execution_id: str
    status: str
    message: str


class ScriptCancelResponse(BaseModel):
    """Response for script cancel operation."""

    execution_id: str
    status: str
    message: str
