"""Template pack schemas for API 2.0 with assets."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import BulkResult, CursorPage, PaginatedResponse

# --- Asset schemas ---


class PackAssetCreate(BaseModel):
    """Asset file to include with a pack (base64-encoded)."""

    path: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Relative asset path, e.g. assets/docker-compose.yml",
    )
    content_base64: str = Field(
        ...,
        min_length=1,
        description="Base64-encoded file content",
    )


class PackAssetResponse(BaseModel):
    """Schema for template asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pack_id: uuid.UUID
    path: str
    size: int = Field(..., ge=0)
    sha: str | None = Field(default=None, max_length=64)
    created_at: datetime
    updated_at: datetime


# --- Pack schemas ---


class PackCreate(BaseModel):
    """Schema for creating a template pack (local upload)."""

    pack_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique pack identifier, e.g. docker-install",
    )
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    version: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Semver version, e.g. 1.0.0",
    )
    author: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list, description="Search tags")
    manifest_sha: str | None = Field(default=None, max_length=64)
    readme: str | None = Field(default=None, description="Markdown README content")
    assets: list[PackAssetCreate] | None = Field(
        default=None,
        description="Optional assets with base64 content",
    )


class PackUpdate(BaseModel):
    """Schema for updating a template pack (partial)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    version: str | None = Field(default=None, min_length=1, max_length=50)
    author: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    manifest_sha: str | None = Field(default=None, max_length=64)
    readme: str | None = None


class PackResponse(BaseModel):
    """Schema for template pack response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registry_id: uuid.UUID | None
    pack_id: str
    name: str
    description: str | None
    version: str
    author: str | None
    tags: list[str] | None
    manifest_sha: str | None
    readme: str | None
    installed_version: str | None
    installed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PackListResponse(PaginatedResponse[PackResponse]):
    """Offset-based paginated list of packs."""


class PackCursorListResponse(CursorPage[PackResponse]):
    """Cursor-based paginated list of packs."""


# --- Bulk operation schemas (2.0 bulk-first, 207 Multi-Status) ---


class BulkPackCreateRequest(BaseModel):
    """Request to create multiple packs (bulk local upload)."""

    items: list[PackCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Template packs to create (1..100)",
    )


class BulkPackResult(BaseModel):
    """Result of a single bulk pack operation item."""

    pack_id: str = Field(..., min_length=1, max_length=100)
    status: Literal["success", "error"]
    id: uuid.UUID | None = Field(default=None, description="Created pack ID on success")
    error: str = Field(default="", description="Error message on failure")
    message: str = Field(default="", description="Human-readable result message")


class BulkPackResponse(BaseModel):
    """Response for bulk pack operation (207 Multi-Status)."""

    total: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[BulkPackResult]


class BulkPackCreateResponse(BulkResult[BulkPackResult]):
    """Generic BulkResult envelope for pack create."""


class BulkPackDeleteRequest(BaseModel):
    """Request to delete multiple packs by ID."""

    pack_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Pack IDs to delete (1..100)",
    )


class BulkPackDeleteResult(BaseModel):
    """Result of a single bulk delete item."""

    pack_id: uuid.UUID
    status: Literal["success", "error"]
    error: str = ""


class BulkPackDeleteResponse(BaseModel):
    """Response for bulk pack delete (207 Multi-Status)."""

    total: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[BulkPackDeleteResult]


# --- Installation schemas ---


class PackInstallResult(BaseModel):
    """Result of installing a single entity from a pack."""

    entity_type: Literal["command", "script"]
    entity_id: uuid.UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    status: Literal["success", "error"]
    error: str = ""


class PackInstallResponse(BaseModel):
    """Response for pack install/update (207 Multi-Status)."""

    pack_id: uuid.UUID
    version: str
    total: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    results: list[PackInstallResult]


class PackUninstallResponse(BaseModel):
    """Response for pack uninstall."""

    pack_id: uuid.UUID
    status: str
    message: str = ""
