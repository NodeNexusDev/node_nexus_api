"""Script execution schemas for API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.application.dto.script_execution import ScriptExecutionStatus
from app.core.types import JsonObject
from app.schemas.script import ScriptStepResult


class ScriptExecutionResponse(BaseModel):
    """Schema for a single script execution record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    script_id: uuid.UUID
    node_id: uuid.UUID | None
    params: JsonObject | None
    status: ScriptExecutionStatus
    steps: list[ScriptStepResult] | None
    started_at: datetime
    finished_at: datetime | None


class ScriptExecutionsRequest(BaseModel):
    """M×N script executions (script_ids × nodes)."""

    script_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    params: dict[str, JsonObject] = Field(default_factory=dict)


class BulkScriptExecutionItem(BaseModel):
    """Result of a single script execution on a single node."""

    script_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None
    node_name: str | None = None
    status: Literal["success", "error"]
    steps: list[ScriptStepResult] = Field(default_factory=list)
    error: str = ""


class BulkScriptExecutionBatchResponse(BaseModel):
    """Batch response for M×N script executions."""

    batch_id: uuid.UUID
    total: int
    succeeded: int
    failed: int
    results: list[BulkScriptExecutionItem]


class ExecutionRetriesRequest(BaseModel):
    """Request to retry multiple executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ExecutionCancelsRequest(BaseModel):
    """Request to cancel multiple executions."""

    execution_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class BulkRetryScriptResult(BaseModel):
    """Result of retrying a single script execution."""

    execution_id: str
    status: Literal["retry_scheduled", "error"]
    message: str = ""


class BulkCancelScriptResult(BaseModel):
    """Result of cancelling a single script execution."""

    execution_id: str
    status: Literal["cancelled", "error"]
    message: str = ""
