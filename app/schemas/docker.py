"""Docker schemas for API."""

from pydantic import BaseModel, Field


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
    env: list[str] | None = None
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
    network_settings: dict | None = Field(default=None, alias="NetworkSettings")

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
