# ruff: noqa: F401, I001
"""Docker schemas — system."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.types import JsonObject


class DockerSystemInfo(BaseModel):
    """Response from ``docker info --format json``."""

    server_version: str = ""
    storage_driver: str = ""
    operating_system: str = ""
    architecture: str = ""
    total_memory: str = ""
    cpus: int = 0
    containers_running: int = 0
    containers_stopped: int = 0
    images: int = 0


class DockerSystemDfItem(BaseModel):
    """A single row from ``docker system df``."""

    type: str
    total_count: int = 0
    active_size: str = "0B"
    reclaimable_size: str = "0B"
    reclaimable_percent: str = "0%"


class DockerPruneResponse(BaseModel):
    """Result of a prune operation."""

    containers_deleted: list[str] = Field(default_factory=list)
    images_deleted: list[str] = Field(default_factory=list)
    space_reclaimed: str = ""


class DockerActionResponse(BaseModel):
    """Result of a simple Docker mutation action."""

    status: str


class DockerContainerRenameResponse(BaseModel):
    """Result of renaming a Docker container."""

    status: str
    new_name: str


class DockerNetworkCreateResponse(BaseModel):
    """Result of creating a Docker network."""

    id: str
    name: str


class DockerVolumeCreateResponse(BaseModel):
    """Result of creating a Docker volume."""

    name: str


class DockerVolumePruneResponse(BaseModel):
    """Result of pruning Docker volumes."""

    output: str


class BulkDockerRequest(BaseModel):
    """Request for bulk Docker operations on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    container_id: str = Field(min_length=1, max_length=255)
    timeout: int | None = Field(default=None, ge=1, le=300)
    command: str | None = Field(
        default=None,
        min_length=1,
        max_length=4096,
        description=(
            "Command to execute. Required for 'exec' action, "
            "ignored for start/stop/restart/remove/inspect/logs/stats."
        ),
    )

    @model_validator(mode="after")
    def _require_targets(self) -> Self:
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerNodeResult(BaseModel):
    """Result of a Docker operation on a single node."""

    node_id: uuid.UUID
    node_name: str
    status: Literal["success", "error"]
    output: str = ""
    error: str = ""


class BulkDockerResponse(BaseModel):
    """Response for bulk Docker operations."""

    action: str
    results: list[BulkDockerNodeResult]
    total: int
    succeeded: int
    failed: int


class BulkDockerPullRequest(BaseModel):
    """Request for bulk Docker image pull on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    image: str = Field(min_length=1, max_length=255)
    timeout: int | None = Field(default=None, ge=1, le=3600)

    @model_validator(mode="after")
    def _require_targets(self) -> Self:
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerPullResult(BaseModel):
    """Result of a Docker image pull on a single node."""

    node_id: uuid.UUID
    node_name: str
    status: Literal["success", "error"]
    output: str = ""
    error: str = ""


class BulkDockerPullResponse(BaseModel):
    """Response for bulk Docker image pull."""

    results: list[BulkDockerPullResult]
    total: int
    succeeded: int
    failed: int


# --- Bulk Docker image remove ---


class BulkDockerImageRemoveRequest(BaseModel):
    """Request to remove Docker images on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    image_id: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def _require_targets(self) -> Self:
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerImageRemoveResult(BaseModel):
    """Result of removing a Docker image on a single node."""

    node_id: uuid.UUID
    node_name: str
    status: Literal["success", "error"]
    output: str = ""
    error: str = ""


class BulkDockerImageRemoveResponse(BaseModel):
    """Response for bulk Docker image remove."""

    results: list[BulkDockerImageRemoveResult]
    total: int
    succeeded: int
    failed: int


# --- Bulk Docker image build ---


class BulkDockerImageBuildRequest(BaseModel):
    """Request to build Docker images on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    dockerfile: str = Field(min_length=1, max_length=4096)
    tag: str = Field(min_length=1, max_length=255)
    build_args: dict[str, str] = Field(default_factory=dict)
    no_cache: bool = False
    timeout: int | None = Field(default=None, ge=1, le=3600)

    @model_validator(mode="after")
    def _require_targets(self) -> Self:
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerImageBuildResult(BaseModel):
    """Result of building a Docker image on a single node."""

    node_id: uuid.UUID
    node_name: str
    status: Literal["success", "error"]
    output: str = ""
    error: str = ""


class BulkDockerImageBuildResponse(BaseModel):
    """Response for bulk Docker image build."""

    results: list[BulkDockerImageBuildResult]
    total: int
    succeeded: int
    failed: int


# ---------------------------------------------------------------------------
# v2 vert bulk schemas (moved from app/api/v2/docker.py)
# ---------------------------------------------------------------------------


class DockerVersionResponse(BaseModel):
    """Response for ``docker version``."""

    server_version: str = ""
    api_version: str = ""
    go_version: str = ""
    git_commit: str = ""
    build_time: str = ""
    os: str = ""
    arch: str = ""


class DockerPortResponse(BaseModel):
    """Response for ``docker port``."""

    output: str
    bindings: str = ""


class DockerWaitResponse(BaseModel):
    """Response for ``docker wait``."""

    exit_code: int


class DockerArchiveResponse(BaseModel):
    """Response for ``docker cp`` archive get."""

    output: str
    path: str
