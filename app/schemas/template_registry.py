"""Template registry schemas for API 2.0."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import BulkResult, CursorPage, PaginatedResponse


class RegistryCreate(BaseModel):
    """Schema for creating a template registry (GitHub repo)."""

    owner: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="GitHub owner or organization",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Repository name",
    )
    github_token: str | None = Field(
        default=None,
        repr=False,
        description="Optional GitHub PAT for private repos",
    )
    default_branch: str = Field(
        default="main",
        min_length=1,
        max_length=100,
        description="Default branch to fetch templates from",
    )


class RegistryUpdate(BaseModel):
    """Schema for updating a template registry (partial)."""

    owner: str | None = Field(default=None, min_length=1, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    github_token: str | None = Field(default=None, repr=False)
    default_branch: str | None = Field(default=None, min_length=1, max_length=100)


class RegistryResponse(BaseModel):
    """Schema for template registry response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner: str
    name: str
    default_branch: str
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RegistryListResponse(PaginatedResponse[RegistryResponse]):
    """Offset-based paginated list of registries."""


class RegistryCursorListResponse(CursorPage[RegistryResponse]):
    """Cursor-based paginated list of registries."""


# --- Sync results (207 Multi-Status) ---


class RegistrySyncItem(BaseModel):
    """Result of syncing a single pack from a registry."""

    pack_id: str = Field(..., min_length=1, max_length=100)
    status: Literal["success", "error"]
    error: str = Field(default="", description="Error message on failure")
    message: str = Field(default="", description="Human-readable result message")


class RegistrySyncResult(BaseModel):
    """Result of syncing a registry (207 Multi-Status)."""

    registry_id: uuid.UUID
    total: int = Field(..., ge=0, description="Total packs discovered")
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[RegistrySyncItem]


class BulkRegistrySyncResult(BulkResult[RegistrySyncItem]):
    """Generic BulkResult envelope for registry sync."""
