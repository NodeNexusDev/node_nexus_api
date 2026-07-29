"""Immutable application DTOs for Docker use cases."""

from dataclasses import dataclass
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
class BulkDockerRequestDTO:
    node_ids: tuple[str, ...]
    container_id: str
    action: str
    timeout: int | None = None
    command: str | None = None


@dataclass(frozen=True, slots=True)
class BulkDockerNodeResultDTO:
    node_id: str
    node_name: str
    status: str
    output: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class BulkDockerResultDTO:
    action: str
    results: tuple[BulkDockerNodeResultDTO, ...]
    total: int
    succeeded: int
    failed: int
