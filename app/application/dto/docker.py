"""Immutable application DTOs for Docker use cases."""

import uuid
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DockerContainerDTO:
    id: str
    names: str
    image: str
    command: str
    created_at: str
    state: str
    status: str
    ports: str | None = None
    networks: str | None = None


@dataclass(frozen=True, slots=True)
class DockerContainerStateDTO:
    status: str
    running: bool
    exit_code: int
    started_at: str | None = None
    finished_at: str | None = None
    oom_killed: bool | None = None


@dataclass(frozen=True, slots=True)
class DockerContainerConfigDTO:
    image: str | None = None
    cmd: tuple[str, ...] | None = None
    hostname: str | None = None


@dataclass(frozen=True, slots=True)
class DockerContainerInspectDTO:
    id: str
    name: str
    state: DockerContainerStateDTO
    config: DockerContainerConfigDTO
    network_settings: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class DockerContainerActionDTO:
    node_id: UUID
    container_id: str
    timeout: int = 10
    force: bool = False


@dataclass(frozen=True, slots=True)
class DockerLogsQueryDTO:
    node_id: UUID
    container_id: str
    tail: int = 100
    since: str | None = None


@dataclass(frozen=True, slots=True)
class DockerExecRequestDTO:
    node_id: UUID
    container_id: str
    command: str
    timeout: int = 30


@dataclass(frozen=True, slots=True)
class DockerExecResultDTO:
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True, slots=True)
class DockerStatsDTO:
    container_id: str
    name: str
    cpu_percent: str
    mem_usage: str
    mem_percent: str
    net_io: str
    block_io: str
    mem_limit: str | None = None
    pids: str | None = None


@dataclass(frozen=True, slots=True)
class DockerImageDTO:
    repository: str
    tag: str
    id: str
    size: str
    created_at: str


@dataclass(frozen=True, slots=True)
class DockerImagePullRequestDTO:
    node_id: UUID
    image: str
    timeout: int = 300


@dataclass(frozen=True, slots=True)
class DockerPullResultDTO:
    image: str
    output: str
    success: bool


@dataclass(frozen=True, slots=True)
class DockerNetworkDTO:
    id: str
    name: str
    driver: str
    scope: str


@dataclass(frozen=True, slots=True)
class DockerVolumeDTO:
    driver: str
    name: str


@dataclass(frozen=True, slots=True)
class ContainerCreateRequestDTO:
    """Validated inputs for ``docker create``."""

    node_id: UUID
    image: str
    name: str | None = None
    command: str | None = None
    ports: tuple[tuple[str, str], ...] = ()
    volumes: tuple[tuple[str, str, str], ...] = ()
    env: tuple[str, ...] = ()
    labels: tuple[tuple[str, str], ...] = ()
    network: str | None = None
    restart_policy: str | None = None


@dataclass(frozen=True, slots=True)
class ContainerCreatedDTO:
    """Result of ``docker create``."""

    id: str
    name: str
    image: str
    status: str = "created"


@dataclass(frozen=True, slots=True)
class DockerImageInspectDTO:
    """Parsed ``docker inspect --type=image`` output."""

    id: str
    repo_tags: tuple[str, ...]
    size: int
    created: str
    architecture: str
    os: str


@dataclass(frozen=True, slots=True)
class DockerImageTagRequestDTO:
    node_id: UUID
    image_id: str
    repo: str
    tag: str


@dataclass(frozen=True, slots=True)
class DockerImageTagResultDTO:
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class DockerImageBuildRequestDTO:
    node_id: UUID
    dockerfile: str
    tag: str
    build_args: tuple[tuple[str, str], ...] = ()
    no_cache: bool = False


@dataclass(frozen=True, slots=True)
class DockerImageBuildResultDTO:
    image_id: str
    tag: str
    output: str


@dataclass(frozen=True, slots=True)
class BulkDockerRequestDTO:
    node_ids: tuple[uuid.UUID, ...]
    container_id: str
    action: str
    timeout: int | None = None
    command: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BulkDockerNodeResultDTO:
    node_id: str
    node_name: str
    status: Literal["success", "error"]
    output: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class BulkDockerResultDTO:
    action: str
    results: tuple[BulkDockerNodeResultDTO, ...]
    total: int
    succeeded: int
    failed: int


@dataclass(frozen=True, slots=True)
class BulkDockerPullResultDTO:
    node_id: str
    node_name: str
    status: Literal["success", "error"]
    output: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class BulkDockerPullResultsDTO:
    results: tuple[BulkDockerPullResultDTO, ...]
    total: int
    succeeded: int
    failed: int
