# ruff: noqa: F401, I001
"""Node schemas — bulk."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.docker_validation import validate_docker_host
from app.core.types import ConnectionType, JsonObject, NodeStatus
from app.schemas.common import CursorPage, PaginatedResponse
from app.schemas.node_schemas.metrics import NodeMetrics
from app.schemas.node_schemas.node import NodeCreate, NodeUpdate


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
    status: Literal["success", "error"]
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
    status: Literal["success", "error"]
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
    status: Literal["success", "error"]
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
    status: Literal["retry_scheduled", "error"]
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
    status: Literal["cancelled", "error"]
    message: str = ""


class BulkCancelCommandResponse(BaseModel):
    """Response for bulk command cancellation."""

    results: list[BulkCancelCommandResult]
    total: int
    succeeded: int
    failed: int


# --- 2.0 bulk-first without bulk keyword ---


class NodeBulkCreateRequest(BaseModel):
    """Bulk create nodes (2.0)."""

    items: list[NodeCreate] = Field(min_length=1, max_length=20)


class NodeBulkCreateResult(BaseModel):
    """Result of creating a single node."""

    node_id: uuid.UUID | None = None
    status: Literal["success", "error"]
    error: str = ""


class NodeBulkCreateResponse(BaseModel):
    """Response for bulk node creation (207 Multi-Status)."""

    total: int
    succeeded: int
    failed: int
    results: list[NodeBulkCreateResult]


class NodeDeletionsRequest(BaseModel):
    """Bulk delete without bulk keyword (2.0)."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class NodeDeletionsResponse(BaseModel):
    """Unified bulk delete response (207)."""

    total: int
    succeeded: int
    failed: int
    results: list[BulkNodeUpdateResult]


class NodeBulkUpdateItem(BaseModel):
    """Single bulk update item."""

    id: uuid.UUID
    changes: NodeUpdate


class NodeBulkUpdatesRequest(BaseModel):
    """Bulk update via PATCH /nodes (2.0)."""

    updates: list[NodeBulkUpdateItem] = Field(min_length=1, max_length=100)


class NodeChecksRequest(BaseModel):
    """Request for bulk checks without bulk keyword."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class NodeMetricsRequest(BaseModel):
    """Request for bulk metrics without bulk keyword."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class CredentialValidationsRequest(BaseModel):
    """Request for credential validations without bulk keyword."""

    ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=100)
    tags: list[str] | None = Field(default=None, min_length=1)
