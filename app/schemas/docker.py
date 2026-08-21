"""Docker schemas for API."""

import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DockerContainer(BaseModel):
    """Container info from `docker ps --format json`.

    Fields match `docker ps --format '{{json .}}'` output:
    - ID, Names, Image, Command, CreatedAt, State, Status, Ports, Networks
    """

    id: str = Field(alias="ID")
    names: str = Field(alias="Names")
    image: str = Field(alias="Image")
    command: str = Field(alias="Command")
    created_at: str = Field(alias="CreatedAt")
    state: str = Field(alias="State")
    status: str = Field(alias="Status")
    ports: str | None = Field(default=None, alias="Ports")
    networks: str | None = Field(default=None, alias="Networks")

    model_config = {"populate_by_name": True}


class DockerContainerState(BaseModel):
    """State info from `docker inspect`."""

    status: str
    running: bool
    exit_code: int
    started_at: str | None = None
    finished_at: str | None = None
    oom_killed: bool | None = None


class DockerContainerConfig(BaseModel):
    """Config info from `docker inspect`."""

    image: str | None = None
    cmd: list[str] | None = None
    hostname: str | None = None


class DockerContainerInspect(BaseModel):
    """Container info from `docker inspect`.

    Fields match `docker inspect {id}` output:
    - Id, Name, State, Config, NetworkSettings
    """

    id: str = Field(alias="Id")
    name: str = Field(alias="Name")
    state: DockerContainerState = Field(alias="State")
    config: DockerContainerConfig = Field(alias="Config")
    network_settings: dict[str, Any] | None = Field(
        default=None, alias="NetworkSettings"
    )

    model_config = {"populate_by_name": True}


class DockerExecRequest(BaseModel):
    """Request to execute a command in a container."""

    command: str = Field(min_length=1, max_length=4096)
    timeout: int = Field(default=30, ge=1, le=600)


class DockerExecResult(BaseModel):
    """Result of command execution in a container."""

    stdout: str
    stderr: str
    exit_code: int


class ContainerVolumeMount(BaseModel):
    """Bind-mount specification for ``docker create``."""

    bind: str = Field(min_length=1, max_length=4096)
    mode: str = Field(default="rw", pattern="^(rw|ro)$")


class ContainerCreateRequest(BaseModel):
    """Request body for ``POST /containers`` (``docker create``)."""

    image: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    command: str | None = Field(default=None, max_length=4096)
    ports: dict[str, str] = Field(default_factory=dict)
    volumes: dict[str, ContainerVolumeMount] = Field(default_factory=dict)
    env: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    network: str | None = Field(default=None, max_length=255)
    restart_policy: str | None = Field(default=None)
    detach: bool = Field(default=True)


class ContainerCreatedResponse(BaseModel):
    """Response body for container creation (HTTP 201)."""

    id: str
    name: str
    image: str
    status: str = "created"


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


class DockerStats(BaseModel):
    """Stats from `docker stats --no-stream --format json`.

    Fields match `docker stats --no-stream --format '{{json .}}'` output:
    - Container, Name, CPUPerc, MemUsage, MemPerc, NetIO, BlockIO, PIDs
    """

    container_id: str = Field(alias="Container")
    name: str = Field(alias="Name")
    cpu_percent: str = Field(alias="CPUPerc")
    mem_usage: str = Field(alias="MemUsage")
    mem_limit: str | None = Field(default=None, alias="MemLimit")
    mem_percent: str = Field(alias="MemPerc")
    net_io: str = Field(alias="NetIO")
    block_io: str = Field(alias="BlockIO")
    pids: str | None = Field(default=None, alias="PIDs")

    model_config = {"populate_by_name": True}


class DockerNetwork(BaseModel):
    """Network info from `docker network ls --format json`.

    Fields: ID, Name, Driver, Scope
    """

    id: str = Field(alias="ID")
    name: str = Field(alias="Name")
    driver: str = Field(alias="Driver")
    scope: str = Field(alias="Scope")

    model_config = {"populate_by_name": True}


class DockerVolume(BaseModel):
    """Volume info from `docker volume ls --format json`.

    Fields: Driver, Name
    """

    driver: str = Field(alias="Driver")
    name: str = Field(alias="Name")

    model_config = {"populate_by_name": True}


class BulkDockerRequest(BaseModel):
    """Request for bulk Docker operations on multiple nodes."""

    node_ids: list[uuid.UUID] = Field(default_factory=list)
    node_tags: list[str] = Field(default_factory=list)
    container_id: str = Field(min_length=1, max_length=255)
    timeout: int | None = Field(default=None, ge=1, le=300)
    command: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def _require_targets(self) -> "BulkDockerRequest":
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerNodeResult(BaseModel):
    """Result of a Docker operation on a single node."""

    node_id: str
    node_name: str
    status: str  # "success" or "error"
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
    def _require_targets(self) -> "BulkDockerPullRequest":
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerPullResult(BaseModel):
    """Result of a Docker image pull on a single node."""

    node_id: str
    node_name: str
    status: str  # "success" or "error"
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
    def _require_targets(self) -> "BulkDockerImageRemoveRequest":
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerImageRemoveResult(BaseModel):
    """Result of removing a Docker image on a single node."""

    node_id: str
    node_name: str
    status: str  # "success" or "error"
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
    def _require_targets(self) -> "BulkDockerImageBuildRequest":
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self


class BulkDockerImageBuildResult(BaseModel):
    """Result of building a Docker image on a single node."""

    node_id: str
    node_name: str
    status: str  # "success" or "error"
    output: str = ""
    error: str = ""


class BulkDockerImageBuildResponse(BaseModel):
    """Response for bulk Docker image build."""

    results: list[BulkDockerImageBuildResult]
    total: int
    succeeded: int
    failed: int
