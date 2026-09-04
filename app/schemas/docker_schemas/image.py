# ruff: noqa: F401, I001
"""Docker schemas — image."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.types import JsonObject


class DockerImageInspectResponse(BaseModel):
    """Parsed image inspect output."""

    id: str
    repo_tags: list[str] = Field(default_factory=list)
    size: int = 0
    created: str = ""
    architecture: str = ""
    os: str = ""


class DockerImageTagRequest(BaseModel):
    """Request body for ``POST /images/{image_id}/tag``."""

    repo: str = Field(min_length=1, max_length=255)
    tag: str = Field(min_length=1, max_length=128)


class DockerImageTagResponse(BaseModel):
    """Response body for image tagging."""

    source: str
    target: str


class DockerImageBuildRequest(BaseModel):
    """Request body for ``POST /images/build``."""

    dockerfile: str = Field(min_length=1, max_length=1_048_576)
    tag: str = Field(min_length=1, max_length=255)
    build_args: dict[str, str] = Field(default_factory=dict)
    no_cache: bool = False


class DockerImageBuildResponse(BaseModel):
    """Response body for image build."""

    image_id: str
    tag: str
    output: str


class DockerImage(BaseModel):
    """Image info from `docker images --format json`.

    Fields match `docker images --format '{{json .}}'` output:
    - Repository, Tag, ID, Size, CreatedAt
    """

    repository: str = Field(alias="Repository")
    tag: str = Field(alias="Tag")
    id: str = Field(alias="ID")
    size: str = Field(alias="Size")
    created_at: str = Field(alias="CreatedAt")

    model_config = {"populate_by_name": True}


class DockerImagePullRequest(BaseModel):
    """Request to pull a Docker image."""

    image: str = Field(min_length=1, max_length=255)
    timeout: int = Field(default=300, ge=1, le=3600)


class DockerPullResult(BaseModel):
    """Result of image pull operation."""

    image: str
    output: str
    success: bool


class ImagePullsRequest(BaseModel):
    """Bulk image pulls."""

    images: list[str] = Field(min_length=1, max_length=100)
    timeout: int = Field(default=300, ge=1, le=3600)


class ImageRemovalsRequest(BaseModel):
    """Bulk image removals."""

    image_ids: list[str] = Field(min_length=1, max_length=100)


class ImageBulkResult(BaseModel):
    """Result of a bulk image action."""

    image: str
    status: Literal["success", "error"]
    error: str = ""
    output: str = ""


class DockerImageHistoryItem(BaseModel):
    """Single history entry."""

    id: str = ""
    created: str = ""
    created_by: str = ""
    size: str = ""
    comment: str = ""


class DockerImageHistoryResponse(BaseModel):
    """Response for ``docker history``."""

    layers: list[DockerImageHistoryItem]


class DockerImagePushRequest(BaseModel):
    """Request to push an image."""

    image: str = Field(min_length=1, max_length=255)
