"""Template registry schemas for API 2.0."""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import BulkResult, SafeName

# Owner/repo names go into the GitHub API URL path — no separators allowed.
_GITHUB_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _check_github_name(value: str) -> str:
    if not _GITHUB_NAME_RE.fullmatch(value):
        raise ValueError(f"Invalid GitHub owner/repo name: {value!r}")
    return value


def _check_optional_github_name(value: str | None) -> str | None:
    if value is None:
        return None
    return _check_github_name(value)


class RegistryCreate(BaseModel):
    """Schema for creating a template registry (GitHub repo)."""

    owner: SafeName = Field(
        ...,
        min_length=1,
        max_length=255,
        description="GitHub owner or organization",
    )
    name: SafeName = Field(
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

    @field_validator("owner", "name")
    @classmethod
    def _validate_names(cls, value: str) -> str:
        return _check_github_name(value)


class RegistryUpdate(BaseModel):
    """Schema for updating a template registry (partial)."""

    owner: SafeName | None = Field(default=None, min_length=1, max_length=255)
    name: SafeName | None = Field(default=None, min_length=1, max_length=255)
    github_token: str | None = Field(default=None, repr=False)
    default_branch: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("owner", "name")
    @classmethod
    def _validate_names(cls, value: str | None) -> str | None:
        return _check_optional_github_name(value)


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
