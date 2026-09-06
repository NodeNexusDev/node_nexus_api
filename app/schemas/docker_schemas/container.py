# ruff: noqa: F401, I001
"""Docker schemas — container."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.types import JsonObject


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
    health: str | None = None
    health_failing_streak: int | None = None
    health_log: list[JsonObject] | None = None


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
    network_settings: JsonObject | None = Field(default=None, alias="NetworkSettings")

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


class ContainerRenameRequest(BaseModel):
    """Request body for renaming a container."""

    new_name: str = Field(min_length=1, max_length=255)


class DockerTopProcess(BaseModel):
    """A single process from ``docker top`` output."""

    values: tuple[str, ...]


class DockerTopResult(BaseModel):
    """Result of ``docker top`` — processes running in a container."""

    titles: tuple[str, ...]
    processes: list[tuple[str, ...]] = Field(default_factory=list)


class ContainerVolumeMount(BaseModel):
    """Bind-mount specification for ``docker create``."""

    bind: str = Field(min_length=1, max_length=4096)
    mode: Literal["rw", "ro"] = Field(default="rw")


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


class ContainerIdsRequest(BaseModel):
    """Bulk container ids (1..100)."""

    container_ids: list[str] = Field(min_length=1, max_length=100)


class ContainerKillsRequest(BaseModel):
    """Bulk kills with signal."""

    container_ids: list[str] = Field(min_length=1, max_length=100)
    signal: str = Field(default="SIGTERM", min_length=1, max_length=20)


class ContainerUpdatesRequest(BaseModel):
    """Bulk updates."""

    container_ids: list[str] = Field(min_length=1, max_length=100)
    memory: str | None = Field(default=None, max_length=64)
    cpus: str | None = Field(default=None, max_length=64)
    restart_policy: str | None = Field(default=None, max_length=64)


class ContainerExecutionsRequest(BaseModel):
    """Bulk executions."""

    container_ids: list[str] = Field(min_length=1, max_length=100)
    command: str = Field(min_length=1, max_length=4096)
    timeout: int = Field(default=30, ge=1, le=600)


class ContainerInspectionsRequest(BaseModel):
    """Bulk inspections."""

    container_ids: list[str] = Field(min_length=1, max_length=100)


class ContainerLogsRequest(BaseModel):
    """Bulk logs."""

    container_ids: list[str] = Field(min_length=1, max_length=100)
    tail: int = Field(default=100, ge=1, le=10000)
    since: str | None = None


class ContainerStatsRequest(BaseModel):
    """Bulk stats."""

    container_ids: list[str] = Field(min_length=1, max_length=100)


class ContainerBulkResult(BaseModel):
    """Result of a bulk container action."""

    container_id: str
    status: Literal["success", "error"]
    error: str = ""
    output: str = ""


class ContainerInspectBulkResult(BaseModel):
    """Bulk inspect result with payload."""

    container_id: str
    status: Literal["success", "error"]
    error: str = ""
    data: DockerContainerInspect | None = None


class ContainerExecBulkResult(BaseModel):
    """Bulk exec result."""

    container_id: str
    status: Literal["success", "error"]
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None


class ContainerLogsBulkResult(BaseModel):
    """Bulk logs result."""

    container_id: str
    status: Literal["success", "error"]
    error: str = ""
    logs: str = ""


class ContainerStatsBulkResult(BaseModel):
    """Bulk stats result."""

    container_id: str
    status: Literal["success", "error"]
    error: str = ""
    stats: DockerStats | None = None


class KillRequest(BaseModel):
    """Single kill request."""

    signal: str = Field(default="SIGTERM", min_length=1, max_length=20)


class UpdateRequest(BaseModel):
    """Single update request."""

    memory: str | None = Field(default=None, max_length=64)
    cpus: str | None = Field(default=None, max_length=64)
    restart_policy: str | None = Field(default=None, max_length=64)
