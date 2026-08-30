"""Compose project schemas for API 2.0 (persistent compose_projects)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import BulkResult, CursorPage, PaginatedResponse


class ComposeCreate(BaseModel):
    """Schema for creating a compose project."""

    project_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Compose project name (unique per node)",
    )
    compose: str = Field(
        ...,
        min_length=1,
        max_length=1048576,
        description="docker-compose YAML content",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for compose (.env key-value)",
    )
    template_pack_id: uuid.UUID | None = Field(
        default=None,
        description="Optional linked template pack",
    )


class ComposeUpdate(BaseModel):
    """Schema for updating a compose project (partial)."""

    compose: str | None = Field(
        default=None,
        min_length=1,
        max_length=1048576,
        description="Updated docker-compose YAML content",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Updated environment variables (replaces existing)",
    )
    template_pack_id: uuid.UUID | None = Field(
        default=None,
        description="Updated template pack link (null to unlink)",
    )


class ComposeResponse(BaseModel):
    """Schema for compose project response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node_id: uuid.UUID
    project_name: str
    compose: str
    env: dict[str, str] | None
    template_pack_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --- List / pagination ---


class ComposeListResponse(PaginatedResponse[ComposeResponse]):
    """Offset-based paginated list of compose projects."""


class ComposeCursorListResponse(CursorPage[ComposeResponse]):
    """Cursor-based paginated list of compose projects."""


# --- Bulk operation schemas (2.0 bulk-first, 207 Multi-Status) ---


class BulkComposeCreateRequest(BaseModel):
    """Request to create multiple compose projects (bulk).

    Used with POST /nodes/{id}/docker/compose/projects/bulk or
    POST /nodes/{id}/docker/compose/projects with items[].
    """

    items: list[ComposeCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Compose projects to create (1..100)",
    )


class BulkComposeCreateItem(BaseModel):
    """Single compose create item for bulk request (alternative flat)."""

    project_name: str = Field(..., min_length=1, max_length=100)
    compose: str = Field(..., min_length=1, max_length=1048576)
    env: dict[str, str] = Field(default_factory=dict)
    template_pack_id: uuid.UUID | None = None


class BulkComposeResult(BaseModel):
    """Result of a single bulk compose operation item."""

    project_name: str = Field(..., min_length=1, max_length=100)
    status: Literal["success", "error"]
    id: uuid.UUID | None = Field(
        default=None,
        description="Created compose project ID on success",
    )
    error: str = Field(default="", description="Error message on failure")
    message: str = Field(default="", description="Human-readable result message")


class BulkComposeResponse(BaseModel):
    """Response for bulk compose create (207 Multi-Status)."""

    total: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[BulkComposeResult]


# Generic envelope alias for 2.0 bulk-first


class BulkComposeCreateResponse(BulkResult[BulkComposeResult]):
    """Generic BulkResult envelope for compose create."""


class BulkComposeDeleteRequest(BaseModel):
    """Request to delete multiple compose projects by project_name."""

    project_names: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Project names to delete (1..100)",
    )


class BulkComposeDeleteResult(BaseModel):
    """Result of a single bulk delete item."""

    project_name: str = Field(..., min_length=1, max_length=100)
    status: Literal["success", "error"]
    error: str = ""


class BulkComposeDeleteResponse(BaseModel):
    """Response for bulk compose delete (207 Multi-Status)."""

    total: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[BulkComposeDeleteResult]


class BulkComposeUpdateItem(BaseModel):
    """Single item for bulk compose update."""

    project_name: str = Field(..., min_length=1, max_length=100)
    changes: ComposeUpdate


class BulkComposeUpdateRequest(BaseModel):
    """Request to update multiple compose projects."""

    updates: list[BulkComposeUpdateItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of {project_name, changes: ComposeUpdate}",
    )


class BulkComposeUpdateResult(BaseModel):
    """Result of a single bulk update item."""

    project_name: str = Field(..., min_length=1, max_length=100)
    status: Literal["success", "error"]
    error: str = ""


class BulkComposeUpdateResponse(BaseModel):
    """Response for bulk compose update (207 Multi-Status)."""

    total: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[BulkComposeUpdateResult]
