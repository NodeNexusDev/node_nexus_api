"""Docker management HTTP adapter v2 with cursor pagination and vert bulk."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from dataclasses import asdict
from typing import Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security, status
from pydantic import BaseModel, Field

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.application.command_policy import command_fingerprint
from app.application.dto.docker import (
    ContainerCreateRequestDTO,
    ContainerRenameRequestDTO,
    DockerImageBuildRequestDTO,
    DockerImageTagRequestDTO,
    NetworkConnectRequestDTO,
    NetworkCreateRequestDTO,
    NetworkDisconnectRequestDTO,
    VolumeCreateRequestDTO,
)
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.docker.image_service import DockerImageService
from app.application.services.docker.resource_service import DockerResourceService
from app.application.services.docker.system_service import DockerSystemService
from app.core.docker_validation import (
    validate_container_id,
    validate_container_new_name,
    validate_volume_name,
)
from app.schemas.common import BulkResult, CursorPage
from app.schemas.docker import (
    ContainerCreatedResponse,
    ContainerCreateRequest,
    ContainerRenameRequest,
    DockerActionResponse,
    DockerContainer,
    DockerContainerInspect,
    DockerContainerRenameResponse,
    DockerExecRequest,
    DockerExecResult,
    DockerImage,
    DockerImageBuildRequest,
    DockerImageBuildResponse,
    DockerImageInspectResponse,
    DockerImagePullRequest,
    DockerImageTagRequest,
    DockerImageTagResponse,
    DockerNetwork,
    DockerNetworkCreateResponse,
    DockerPruneResponse,
    DockerPullResult,
    DockerStats,
    DockerSystemDfItem,
    DockerSystemInfo,
    DockerTopResult,
    DockerVolume,
    DockerVolumeCreateResponse,
    DockerVolumePruneResponse,
    NetworkConnectRequest,
    NetworkCreateRequest,
    NetworkDisconnectRequest,
    NetworkInspectResponse,
    VolumeCreateRequest,
    VolumeInspectResponse,
)

audit = structlog.get_logger("audit")
router = APIRouter(
    prefix="/nodes/{node_id}/docker", tags=["docker"], route_class=DishkaRoute
)


# ---------------------------------------------------------------------------
# Cursor helpers (offset-based for Docker lists)
# ---------------------------------------------------------------------------


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor for pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


def _paginate_offset[T](
    items: list[T], cursor: str | None, limit: int
) -> tuple[list[T], str | None, bool]:
    """Slice items by offset cursor."""
    offset = 0
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    sliced = items[offset : offset + limit]
    has_more = (offset + len(sliced)) < len(items)
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return sliced, next_cursor, has_more


# ---------------------------------------------------------------------------
# Local schemas for v2 vert bulk (no bulk keyword, no fleet)
# ---------------------------------------------------------------------------


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


class ImagePullsRequest(BaseModel):
    """Bulk image pulls."""

    images: list[str] = Field(min_length=1, max_length=100)
    timeout: int = Field(default=300, ge=1, le=3600)


class ImageRemovalsRequest(BaseModel):
    """Bulk image removals."""

    image_ids: list[str] = Field(min_length=1, max_length=100)


class NetworkRemovalsRequest(BaseModel):
    """Bulk network removals."""

    network_ids: list[str] = Field(min_length=1, max_length=100)


class VolumeRemovalsRequest(BaseModel):
    """Bulk volume removals."""

    volume_names: list[str] = Field(min_length=1, max_length=100)


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


class ImageBulkResult(BaseModel):
    """Result of a bulk image action."""

    image: str
    status: Literal["success", "error"]
    error: str = ""
    output: str = ""


class NetworkBulkResult(BaseModel):
    """Result of a bulk network action."""

    network_id: str
    status: Literal["success", "error"]
    error: str = ""


class VolumeBulkResult(BaseModel):
    """Result of a bulk volume action."""

    volume_name: str
    status: Literal["success", "error"]
    error: str = ""


class KillRequest(BaseModel):
    """Single kill request."""

    signal: str = Field(default="SIGTERM", min_length=1, max_length=20)


class UpdateRequest(BaseModel):
    """Single update request."""

    memory: str | None = Field(default=None, max_length=64)
    cpus: str | None = Field(default=None, max_length=64)
    restart_policy: str | None = Field(default=None, max_length=64)


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


# ---------------------------------------------------------------------------
# Containers — create & lists with cursor pagination
# ---------------------------------------------------------------------------


@router.post(
    "/containers",
    response_model=ContainerCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
@inject
async def create_container(
    node_id: uuid.UUID,
    data: ContainerCreateRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> ContainerCreatedResponse:
    """Create a container on a Docker node via ``docker create``."""
    audit.info(
        "api.v2.docker.containers.create",
        node_id=str(node_id),
        image=data.image,
        name=data.name,
    )
    request = ContainerCreateRequestDTO(
        node_id=node_id,
        image=data.image,
        name=data.name,
        command=data.command,
        ports=tuple(data.ports.items()),
        volumes=tuple((hp, m.bind, m.mode) for hp, m in data.volumes.items()),
        env=tuple(data.env),
        labels=tuple(data.labels.items()),
        network=data.network,
        restart_policy=data.restart_policy,
    )
    result = await service.create_container(request)
    return ContainerCreatedResponse.model_validate(result, from_attributes=True)


@router.get("/containers", response_model=CursorPage[DockerContainer])
@inject
async def list_containers(
    node_id: uuid.UUID,
    service: FromDishka[DockerContainerService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    all: bool = Query(False, description="Show stopped containers"),  # noqa: A002
    _key: Principal = Security(get_current_principal),
) -> CursorPage[DockerContainer]:
    """List containers on a Docker node with cursor pagination."""
    audit.info("api.v2.docker.containers.list", node_id=str(node_id), all=all)
    items = [
        DockerContainer.model_validate(item, from_attributes=True)
        for item in await service.list_containers(node_id, all=all)
    ]
    sliced, next_cursor, has_more = _paginate_offset(items, cursor, limit)
    return CursorPage[DockerContainer](
        items=sliced, next_cursor=next_cursor, has_more=has_more, limit=limit
    )


@router.get("/containers/{container_id}", response_model=DockerContainerInspect)
@inject
async def get_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(get_current_principal),
) -> DockerContainerInspect:
    """Get container details."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.get", node_id=str(node_id), container_id=validated_id
    )
    result = await service.get_container(node_id, validated_id)
    payload = asdict(result)
    payload["network_settings"] = dict(result.network_settings)
    return DockerContainerInspect.model_validate(payload)


# ---------------------------------------------------------------------------
# Containers — single lifecycle
# ---------------------------------------------------------------------------


@router.post("/containers/{container_id}/start", status_code=204)
@inject
async def start_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Start a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.start",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.start_container(node_id, validated_id)


@router.post("/containers/{container_id}/stop", status_code=204)
@inject
async def stop_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    timeout: int = Query(10, ge=1, le=300),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Stop a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.stop", node_id=str(node_id), container_id=validated_id
    )
    await service.stop_container(node_id, validated_id, timeout=timeout)


@router.post("/containers/{container_id}/restart", status_code=204)
@inject
async def restart_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    timeout: int = Query(10, ge=1, le=300),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Restart a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.restart",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.restart_container(node_id, validated_id, timeout=timeout)


@router.delete("/containers/{container_id}", status_code=204)
@inject
async def remove_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    force: bool = Query(False),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.remove",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.remove_container(node_id, validated_id, force=force)


@router.get("/containers/{container_id}/logs", response_model=str)
@inject
async def get_logs(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    tail: int = Query(100, ge=1, le=10000),
    since: str | None = Query(None),
    _key: Principal = Security(get_current_principal),
) -> str:
    """Get container logs."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.logs", node_id=str(node_id), container_id=validated_id
    )
    return await service.get_logs(node_id, validated_id, tail=tail, since=since)


@router.post("/containers/{container_id}/exec", response_model=DockerExecResult)
@inject
async def exec_command(
    node_id: uuid.UUID,
    container_id: str,
    data: DockerExecRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerExecResult:
    """Execute a command in a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.exec",
        node_id=str(node_id),
        container_id=validated_id,
        command_fingerprint=command_fingerprint(data.command),
        command_length=len(data.command),
    )
    result = await service.exec_command(
        node_id, validated_id, data.command, timeout=data.timeout
    )
    return DockerExecResult.model_validate(result, from_attributes=True)


@router.post("/containers/{container_id}/pause", response_model=DockerActionResponse)
@inject
async def pause_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Pause a running container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.pause",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.pause_container(node_id, validated_id)
    return DockerActionResponse(status="paused")


@router.post("/containers/{container_id}/unpause", response_model=DockerActionResponse)
@inject
async def unpause_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Unpause a paused container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.unpause",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.unpause_container(node_id, validated_id)
    return DockerActionResponse(status="unpaused")


@router.post(
    "/containers/{container_id}/rename",
    response_model=DockerContainerRenameResponse,
)
@inject
async def rename_container(
    node_id: uuid.UUID,
    container_id: str,
    data: ContainerRenameRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerContainerRenameResponse:
    """Rename a container."""
    validated_id = validate_container_id(container_id)
    new_name = validate_container_new_name(data.new_name)
    audit.info(
        "api.v2.docker.containers.rename",
        node_id=str(node_id),
        container_id=validated_id,
        new_name=new_name,
    )
    await service.rename_container(
        ContainerRenameRequestDTO(
            node_id=node_id,
            container_id=validated_id,
            new_name=new_name,
        )
    )
    return DockerContainerRenameResponse(status="renamed", new_name=new_name)


@router.get("/containers/{container_id}/top", response_model=DockerTopResult)
@inject
async def top_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(get_current_principal),
) -> DockerTopResult:
    """List processes running inside a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.top",
        node_id=str(node_id),
        container_id=validated_id,
    )
    result = await service.top_container(node_id, validated_id)
    return DockerTopResult(
        titles=result.titles,
        processes=[list(p) for p in result.processes],
    )


@router.get("/containers/{container_id}/stats", response_model=DockerStats)
@inject
async def get_stats(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(get_current_principal),
) -> DockerStats:
    """Get container stats."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.stats",
        node_id=str(node_id),
        container_id=validated_id,
    )
    result = await service.get_stats(node_id, validated_id)
    return DockerStats.model_validate(result, from_attributes=True)


# ---------------------------------------------------------------------------
# Containers — new single endpoints (kill, update, archive, port, wait)
# ---------------------------------------------------------------------------


@router.post("/containers/{container_id}/kill", response_model=DockerActionResponse)
@inject
async def kill_container(
    node_id: uuid.UUID,
    container_id: str,
    data: KillRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Kill a container with a signal."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.kill",
        node_id=str(node_id),
        container_id=validated_id,
        signal=data.signal,
    )
    await service.kill_container(node_id, validated_id, signal=data.signal)
    return DockerActionResponse(status="killed")


@router.post("/containers/{container_id}/update", response_model=DockerActionResponse)
@inject
async def update_container(
    node_id: uuid.UUID,
    container_id: str,
    data: UpdateRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Update a container (memory, cpus, restart_policy)."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.update",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.update_container(
        node_id,
        validated_id,
        memory=data.memory,
        cpus=data.cpus,
        restart_policy=data.restart_policy,
    )
    return DockerActionResponse(status="updated")


@router.get("/containers/{container_id}/archive", response_model=DockerArchiveResponse)
@inject
async def get_archive(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    path: str = Query(..., min_length=1, max_length=4096),
    _key: Principal = Security(get_current_principal),
) -> DockerArchiveResponse:
    """Copy a file from a container (docker cp)."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.archive.get",
        node_id=str(node_id),
        container_id=validated_id,
        path=path,
    )
    output = await service.get_archive(node_id, validated_id, path)
    return DockerArchiveResponse(output=output, path=path)


@router.put("/containers/{container_id}/archive", response_model=DockerActionResponse)
@inject
async def put_archive(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    path: str = Query(..., min_length=1, max_length=4096),
    data: str = Query("", description="Data to copy into container"),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Copy data into a container (docker cp)."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.archive.put",
        node_id=str(node_id),
        container_id=validated_id,
        path=path,
    )
    await service.put_archive(node_id, validated_id, path, data)
    return DockerActionResponse(status="copied")


@router.get("/containers/{container_id}/port", response_model=DockerPortResponse)
@inject
async def get_port(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    private_port: str | None = Query(None, max_length=64),
    _key: Principal = Security(get_current_principal),
) -> DockerPortResponse:
    """Return port bindings for a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.port",
        node_id=str(node_id),
        container_id=validated_id,
    )
    output = await service.get_port(node_id, validated_id, private_port=private_port)
    return DockerPortResponse(output=output, bindings=output)


@router.post("/containers/{container_id}/wait", response_model=DockerWaitResponse)
@inject
async def wait_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    timeout: int | None = Query(None, ge=1, le=600),
    _key: Principal = Security(get_current_principal),
) -> DockerWaitResponse:
    """Wait for a container to exit."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.v2.docker.containers.wait",
        node_id=str(node_id),
        container_id=validated_id,
    )
    code = await service.wait_container(node_id, validated_id, timeout=timeout)
    return DockerWaitResponse(exit_code=code)


# ---------------------------------------------------------------------------
# Containers — vert bulk without bulk keyword, without fleet (207)
# ---------------------------------------------------------------------------


@router.post("/containers/starts", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_starts(
    node_id: uuid.UUID,
    data: ContainerIdsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Start multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.starts",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.start_container(node_id, validated)
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/stops", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_stops(
    node_id: uuid.UUID,
    data: ContainerIdsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    timeout: int = Query(10, ge=1, le=300),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Stop multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.stops",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.stop_container(node_id, validated, timeout=timeout)
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/restarts", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_restarts(
    node_id: uuid.UUID,
    data: ContainerIdsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    timeout: int = Query(10, ge=1, le=300),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Restart multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.restarts",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.restart_container(node_id, validated, timeout=timeout)
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/removals", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_removals(
    node_id: uuid.UUID,
    data: ContainerIdsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    force: bool = Query(False),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Remove multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.removals",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.remove_container(node_id, validated, force=force)
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/pauses", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_pauses(
    node_id: uuid.UUID,
    data: ContainerIdsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Pause multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.pauses",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.pause_container(node_id, validated)
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/unpauses", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_unpauses(
    node_id: uuid.UUID,
    data: ContainerIdsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Unpause multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.unpauses",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.unpause_container(node_id, validated)
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/kills", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_kills(
    node_id: uuid.UUID,
    data: ContainerKillsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Kill multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.kills",
        node_id=str(node_id),
        count=len(data.container_ids),
        signal=data.signal,
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.kill_container(node_id, validated, signal=data.signal)
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/updates", response_model=BulkResult[ContainerBulkResult])
@inject
async def bulk_updates(
    node_id: uuid.UUID,
    data: ContainerUpdatesRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerBulkResult]:
    """Update multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.updates",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerBulkResult:
        try:
            validated = validate_container_id(cid)
            await service.update_container(
                node_id,
                validated,
                memory=data.memory,
                cpus=data.cpus,
                restart_policy=data.restart_policy,
            )
            return ContainerBulkResult(container_id=cid, status="success")
        except Exception as exc:  # noqa: BLE001
            return ContainerBulkResult(container_id=cid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post(
    "/containers/executions", response_model=BulkResult[ContainerExecBulkResult]
)
@inject
async def bulk_executions(
    node_id: uuid.UUID,
    data: ContainerExecutionsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerExecBulkResult]:
    """Execute a command in multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.executions",
        node_id=str(node_id),
        count=len(data.container_ids),
        command_fingerprint=command_fingerprint(data.command),
    )

    async def _one(cid: str) -> ContainerExecBulkResult:
        try:
            validated = validate_container_id(cid)
            res = await service.exec_command(
                node_id, validated, data.command, timeout=data.timeout
            )
            st: Literal["success", "error"] = (
                "success" if res.exit_code == 0 else "error"
            )
            return ContainerExecBulkResult(
                container_id=cid,
                status=st,
                stdout=res.stdout,
                stderr=res.stderr,
                exit_code=res.exit_code,
                error="" if st == "success" else res.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerExecBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerExecBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post(
    "/containers/inspections", response_model=BulkResult[ContainerInspectBulkResult]
)
@inject
async def bulk_inspections(
    node_id: uuid.UUID,
    data: ContainerInspectionsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(get_current_principal),
) -> BulkResult[ContainerInspectBulkResult]:
    """Inspect multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.inspections",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerInspectBulkResult:
        try:
            validated = validate_container_id(cid)
            res = await service.get_container(node_id, validated)
            payload = asdict(res)
            payload["network_settings"] = dict(res.network_settings)
            insp = DockerContainerInspect.model_validate(payload)
            return ContainerInspectBulkResult(
                container_id=cid, status="success", data=insp
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerInspectBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerInspectBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/logs", response_model=BulkResult[ContainerLogsBulkResult])
@inject
async def bulk_logs(
    node_id: uuid.UUID,
    data: ContainerLogsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(get_current_principal),
) -> BulkResult[ContainerLogsBulkResult]:
    """Get logs from multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.logs.bulk",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerLogsBulkResult:
        try:
            validated = validate_container_id(cid)
            logs = await service.get_logs(
                node_id, validated, tail=data.tail, since=data.since
            )
            return ContainerLogsBulkResult(
                container_id=cid, status="success", logs=logs
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerLogsBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerLogsBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/containers/stats", response_model=BulkResult[ContainerStatsBulkResult])
@inject
async def bulk_stats(
    node_id: uuid.UUID,
    data: ContainerStatsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(get_current_principal),
) -> BulkResult[ContainerStatsBulkResult]:
    """Get stats from multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.stats.bulk",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerStatsBulkResult:
        try:
            validated = validate_container_id(cid)
            res = await service.get_stats(node_id, validated)
            stats = DockerStats.model_validate(res, from_attributes=True)
            return ContainerStatsBulkResult(
                container_id=cid, status="success", stats=stats
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerStatsBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    results = await asyncio.gather(*(_one(cid) for cid in data.container_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ContainerStatsBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


# ---------------------------------------------------------------------------
# Images — cursor pagination + single + bulk
# ---------------------------------------------------------------------------


@router.get("/images", response_model=CursorPage[DockerImage])
@inject
async def list_images(
    node_id: uuid.UUID,
    service: FromDishka[DockerImageService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _key: Principal = Security(get_current_principal),
) -> CursorPage[DockerImage]:
    """List images on a Docker node with cursor pagination."""
    audit.info("api.v2.docker.images.list", node_id=str(node_id))
    items = [
        DockerImage.model_validate(item, from_attributes=True)
        for item in await service.list_images(node_id)
    ]
    sliced, next_cursor, has_more = _paginate_offset(items, cursor, limit)
    return CursorPage[DockerImage](
        items=sliced, next_cursor=next_cursor, has_more=has_more, limit=limit
    )


@router.post("/images/pull", response_model=DockerPullResult)
@inject
async def pull_image(
    node_id: uuid.UUID,
    data: DockerImagePullRequest,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPullResult:
    """Pull a Docker image."""
    audit.info("api.v2.docker.images.pull", node_id=str(node_id), image=data.image)
    result = await service.pull_image(node_id, data.image, timeout=data.timeout)
    return DockerPullResult.model_validate(result, from_attributes=True)


@router.post("/images/build", response_model=DockerImageBuildResponse)
@inject
async def build_image(
    node_id: uuid.UUID,
    data: DockerImageBuildRequest,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerImageBuildResponse:
    """Build a Docker image from a Dockerfile piped through stdin."""
    audit.info(
        "api.v2.docker.images.build",
        node_id=str(node_id),
        tag=data.tag,
        no_cache=data.no_cache,
    )
    request = DockerImageBuildRequestDTO(
        node_id=node_id,
        dockerfile=data.dockerfile,
        tag=data.tag,
        build_args=tuple(data.build_args.items()),
        no_cache=data.no_cache,
    )
    result = await service.build_image(request)
    return DockerImageBuildResponse.model_validate(result, from_attributes=True)


@router.post("/images/pulls", response_model=BulkResult[ImageBulkResult])
@inject
async def bulk_pulls(
    node_id: uuid.UUID,
    data: ImagePullsRequest,
    service: FromDishka[DockerImageService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ImageBulkResult]:
    """Pull multiple images (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.images.pulls", node_id=str(node_id), count=len(data.images)
    )

    async def _one(image: str) -> ImageBulkResult:
        try:
            res = await service.pull_image(node_id, image, timeout=data.timeout)
            st: Literal["success", "error"] = "success" if res.success else "error"
            return ImageBulkResult(
                image=image,
                status=st,
                output=res.output,
                error="" if st == "success" else res.output,
            )
        except Exception as exc:  # noqa: BLE001
            return ImageBulkResult(image=image, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(img) for img in data.images))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ImageBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/images/removals", response_model=BulkResult[ImageBulkResult])
@inject
async def bulk_image_removals(
    node_id: uuid.UUID,
    data: ImageRemovalsRequest,
    service: FromDishka[DockerImageService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ImageBulkResult]:
    """Remove multiple images (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.images.removals", node_id=str(node_id), count=len(data.image_ids)
    )

    async def _one(image_id: str) -> ImageBulkResult:
        try:
            await service.remove_image(node_id, image_id)
            return ImageBulkResult(image=image_id, status="success")
        except Exception as exc:  # noqa: BLE001
            return ImageBulkResult(image=image_id, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(iid) for iid in data.image_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ImageBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.get(
    "/images/{image_id:path}/history", response_model=DockerImageHistoryResponse
)
@inject
async def image_history(
    node_id: uuid.UUID,
    image_id: str,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(get_current_principal),
) -> DockerImageHistoryResponse:
    """Return image history (docker history)."""
    audit.info("api.v2.docker.images.history", node_id=str(node_id), image_id=image_id)
    items = await service.image_history(node_id, image_id)
    layers = []
    for item in items:
        layers.append(
            DockerImageHistoryItem(
                id=str(item.get("ID", "")),
                created=str(item.get("CreatedAt", item.get("Created", ""))),
                created_by=str(item.get("CreatedBy", "")),
                size=str(item.get("Size", "")),
                comment=str(item.get("Comment", "")),
            )
        )
    return DockerImageHistoryResponse(layers=layers)


@router.post("/images/{image_id:path}/tag", response_model=DockerImageTagResponse)
@inject
async def tag_image(
    node_id: uuid.UUID,
    image_id: str,
    data: DockerImageTagRequest,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerImageTagResponse:
    """Tag a Docker image."""
    audit.info(
        "api.v2.docker.images.tag",
        node_id=str(node_id),
        image_id=image_id,
        repo=data.repo,
        tag=data.tag,
    )
    request = DockerImageTagRequestDTO(
        node_id=node_id, image_id=image_id, repo=data.repo, tag=data.tag
    )
    result = await service.tag_image(request)
    return DockerImageTagResponse.model_validate(result, from_attributes=True)


@router.post("/images/{image_id:path}/push", response_model=DockerPullResult)
@inject
async def push_image(
    node_id: uuid.UUID,
    image_id: str,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPullResult:
    """Push a Docker image."""
    audit.info("api.v2.docker.images.push", node_id=str(node_id), image=image_id)
    result = await service.push_image(node_id, image_id)
    return DockerPullResult.model_validate(result, from_attributes=True)


@router.get("/images/{image_id:path}", response_model=DockerImageInspectResponse)
@inject
async def inspect_image(
    node_id: uuid.UUID,
    image_id: str,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(get_current_principal),
) -> DockerImageInspectResponse:
    """Inspect a Docker image."""
    audit.info("api.v2.docker.images.inspect", node_id=str(node_id), image_id=image_id)
    result = await service.inspect_image(node_id, image_id)
    return DockerImageInspectResponse.model_validate(result, from_attributes=True)


@router.delete("/images/{image_id:path}", status_code=204)
@inject
async def remove_image(
    node_id: uuid.UUID,
    image_id: str,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a Docker image."""
    audit.info("api.v2.docker.images.remove", node_id=str(node_id), image_id=image_id)
    await service.remove_image(node_id, image_id)


@router.post("/images/push", response_model=DockerPullResult)
@inject
async def push_image_body(
    node_id: uuid.UUID,
    data: DockerImagePushRequest,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPullResult:
    """Push a Docker image (body variant)."""
    audit.info("api.v2.docker.images.push.body", node_id=str(node_id), image=data.image)
    result = await service.push_image(node_id, data.image)
    return DockerPullResult.model_validate(result, from_attributes=True)


# ---------------------------------------------------------------------------
# Networks — cursor pagination + CRUD + bulk + prune
# ---------------------------------------------------------------------------


@router.get("/networks", response_model=CursorPage[DockerNetwork])
@inject
async def list_networks(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _key: Principal = Security(get_current_principal),
) -> CursorPage[DockerNetwork]:
    """List Docker networks with cursor pagination."""
    audit.info("api.v2.docker.networks.list", node_id=str(node_id))
    items = [
        DockerNetwork.model_validate(item, from_attributes=True)
        for item in await service.list_networks(node_id)
    ]
    sliced, next_cursor, has_more = _paginate_offset(items, cursor, limit)
    return CursorPage[DockerNetwork](
        items=sliced, next_cursor=next_cursor, has_more=has_more, limit=limit
    )


@router.post(
    "/networks",
    response_model=DockerNetworkCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@inject
async def create_network(
    node_id: uuid.UUID,
    data: NetworkCreateRequest,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerNetworkCreateResponse:
    """Create a Docker network."""
    audit.info("api.v2.docker.networks.create", node_id=str(node_id), name=data.name)
    network_id = await service.create_network(
        NetworkCreateRequestDTO(
            node_id=node_id,
            name=data.name,
            driver=data.driver,
            subnet=data.subnet,
            gateway=data.gateway,
        )
    )
    return DockerNetworkCreateResponse(id=network_id, name=data.name)


@router.post("/networks/removals", response_model=BulkResult[NetworkBulkResult])
@inject
async def bulk_network_removals(
    node_id: uuid.UUID,
    data: NetworkRemovalsRequest,
    service: FromDishka[DockerResourceService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[NetworkBulkResult]:
    """Remove multiple networks (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.networks.removals",
        node_id=str(node_id),
        count=len(data.network_ids),
    )

    async def _one(nid: str) -> NetworkBulkResult:
        try:
            validated = validate_container_id(nid)
            await service.remove_network(node_id, validated)
            return NetworkBulkResult(network_id=nid, status="success")
        except Exception as exc:  # noqa: BLE001
            return NetworkBulkResult(network_id=nid, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(nid) for nid in data.network_ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[NetworkBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post("/networks/prune", response_model=DockerVolumePruneResponse)
@inject
async def prune_networks(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerVolumePruneResponse:
    """Prune unused Docker networks."""
    audit.info("api.v2.docker.networks.prune", node_id=str(node_id))
    output = await service.prune_networks(node_id)
    return DockerVolumePruneResponse(output=output)


@router.get("/networks/{network_id}", response_model=NetworkInspectResponse)
@inject
async def inspect_network(
    node_id: uuid.UUID,
    network_id: str,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(get_current_principal),
) -> NetworkInspectResponse:
    """Inspect a Docker network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.inspect",
        node_id=str(node_id),
        network_id=validated_id,
    )
    result = await service.inspect_network(node_id, validated_id)
    return NetworkInspectResponse(
        id=result.id,
        name=result.name,
        driver=result.driver,
        scope=result.scope,
        subnet=result.subnet,
        gateway=result.gateway,
        containers=[
            {
                "name": cdata.get("Name", cid),
                "ipv4_address": cdata.get("IPv4Address", ""),
            }
            for cid, cdata in result.containers
        ],
    )


@router.delete("/networks/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def remove_network(
    node_id: uuid.UUID,
    network_id: str,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a Docker network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.remove",
        node_id=str(node_id),
        network_id=validated_id,
    )
    await service.remove_network(node_id, validated_id)


@router.post("/networks/{network_id}/connect", response_model=DockerActionResponse)
@inject
async def connect_to_network(
    node_id: uuid.UUID,
    network_id: str,
    data: NetworkConnectRequest,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Connect a container to a network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.connect",
        node_id=str(node_id),
        network_id=validated_id,
        container_id=data.container_id,
    )
    await service.connect_to_network(
        NetworkConnectRequestDTO(
            node_id=node_id,
            network_id=validated_id,
            container_id=data.container_id,
            ip_address=data.ip_address,
        )
    )
    return DockerActionResponse(status="connected")


@router.post("/networks/{network_id}/disconnect", response_model=DockerActionResponse)
@inject
async def disconnect_from_network(
    node_id: uuid.UUID,
    network_id: str,
    data: NetworkDisconnectRequest,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Disconnect a container from a network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.disconnect",
        node_id=str(node_id),
        network_id=validated_id,
        container_id=data.container_id,
    )
    await service.disconnect_from_network(
        NetworkDisconnectRequestDTO(
            node_id=node_id,
            network_id=validated_id,
            container_id=data.container_id,
            force=data.force,
        )
    )
    return DockerActionResponse(status="disconnected")


# ---------------------------------------------------------------------------
# Volumes — cursor pagination + CRUD + bulk + prune
# ---------------------------------------------------------------------------


@router.get("/volumes", response_model=CursorPage[DockerVolume])
@inject
async def list_volumes(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _key: Principal = Security(get_current_principal),
) -> CursorPage[DockerVolume]:
    """List Docker volumes with cursor pagination."""
    audit.info("api.v2.docker.volumes.list", node_id=str(node_id))
    items = [
        DockerVolume.model_validate(item, from_attributes=True)
        for item in await service.list_volumes(node_id)
    ]
    sliced, next_cursor, has_more = _paginate_offset(items, cursor, limit)
    return CursorPage[DockerVolume](
        items=sliced, next_cursor=next_cursor, has_more=has_more, limit=limit
    )


@router.post(
    "/volumes",
    response_model=DockerVolumeCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@inject
async def create_volume(
    node_id: uuid.UUID,
    data: VolumeCreateRequest,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerVolumeCreateResponse:
    """Create a Docker volume."""
    audit.info("api.v2.docker.volumes.create", node_id=str(node_id))
    volume_name = await service.create_volume(
        VolumeCreateRequestDTO(
            node_id=node_id,
            name=data.name,
            driver=data.driver,
        )
    )
    return DockerVolumeCreateResponse(name=volume_name)


@router.post("/volumes/removals", response_model=BulkResult[VolumeBulkResult])
@inject
async def bulk_volume_removals(
    node_id: uuid.UUID,
    data: VolumeRemovalsRequest,
    service: FromDishka[DockerResourceService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[VolumeBulkResult]:
    """Remove multiple volumes (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.volumes.removals",
        node_id=str(node_id),
        count=len(data.volume_names),
    )

    async def _one(vname: str) -> VolumeBulkResult:
        try:
            validated = validate_volume_name(vname)
            await service.remove_volume(node_id, validated)
            return VolumeBulkResult(volume_name=vname, status="success")
        except Exception as exc:  # noqa: BLE001
            return VolumeBulkResult(volume_name=vname, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(v) for v in data.volume_names))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[VolumeBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.get("/volumes/{volume_name}", response_model=VolumeInspectResponse)
@inject
async def inspect_volume(
    node_id: uuid.UUID,
    volume_name: str,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(get_current_principal),
) -> VolumeInspectResponse:
    """Inspect a Docker volume."""
    validated_name = validate_volume_name(volume_name)
    audit.info(
        "api.v2.docker.volumes.inspect", node_id=str(node_id), name=validated_name
    )
    result = await service.inspect_volume(node_id, validated_name)
    return VolumeInspectResponse(
        name=result.name,
        driver=result.driver,
        mountpoint=result.mountpoint,
        labels=dict(result.labels),
    )


@router.delete("/volumes/{volume_name}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def remove_volume(
    node_id: uuid.UUID,
    volume_name: str,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a Docker volume."""
    validated_name = validate_volume_name(volume_name)
    audit.info(
        "api.v2.docker.volumes.remove", node_id=str(node_id), name=validated_name
    )
    await service.remove_volume(node_id, validated_name)


@router.post("/volumes/prune", response_model=DockerVolumePruneResponse)
@inject
async def prune_volumes(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerVolumePruneResponse:
    """Prune unused Docker volumes."""
    audit.info("api.v2.docker.volumes.prune", node_id=str(node_id))
    output = await service.prune_volumes(node_id)
    return DockerVolumePruneResponse(output=output)


# ---------------------------------------------------------------------------
# System — info, version, df, prune (containers, images, system)
# ---------------------------------------------------------------------------


@router.get("/system/info", response_model=DockerSystemInfo)
@inject
async def system_info(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(get_current_principal),
) -> DockerSystemInfo:
    """Return Docker system information."""
    audit.info("api.v2.docker.system.info", node_id=str(node_id))
    result = await service.info(node_id)
    return DockerSystemInfo.model_validate(result, from_attributes=True)


@router.get("/system/version", response_model=DockerVersionResponse)
@inject
async def system_version(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(get_current_principal),
) -> DockerVersionResponse:
    """Return Docker version."""
    audit.info("api.v2.docker.system.version", node_id=str(node_id))
    result = await service.version(node_id)
    return DockerVersionResponse(
        server_version=result.server_version,
        api_version=result.api_version,
        go_version=result.go_version,
        git_commit=result.git_commit,
        build_time=result.build_time,
        os=result.os,
        arch=result.arch,
    )


@router.get("/system/df", response_model=list[DockerSystemDfItem])
@inject
async def system_df(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(get_current_principal),
) -> list[DockerSystemDfItem]:
    """Return Docker disk usage."""
    audit.info("api.v2.docker.system.df", node_id=str(node_id))
    results = await service.disk_usage(node_id)
    return [DockerSystemDfItem.model_validate(r, from_attributes=True) for r in results]


@router.post("/system/prune", response_model=DockerPruneResponse)
@inject
async def system_prune(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    volumes: bool = Query(False),
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPruneResponse:
    """Prune system (docker system prune)."""
    audit.info("api.v2.docker.system.prune", node_id=str(node_id), volumes=volumes)
    result = await service.system_prune(node_id, volumes=volumes)
    return DockerPruneResponse(
        containers_deleted=list(result.containers_deleted),
        images_deleted=list(result.images_deleted),
        space_reclaimed=result.space_reclaimed,
    )


@router.post("/containers/prune", response_model=DockerPruneResponse)
@inject
async def prune_containers(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPruneResponse:
    """Prune stopped containers."""
    audit.info("api.v2.docker.containers.prune", node_id=str(node_id))
    result = await service.prune_containers(node_id)
    return DockerPruneResponse(
        containers_deleted=list(result.containers_deleted),
        space_reclaimed=result.space_reclaimed,
    )


@router.post("/images/prune", response_model=DockerPruneResponse)
@inject
async def prune_images(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPruneResponse:
    """Prune unused images."""
    audit.info("api.v2.docker.images.prune", node_id=str(node_id))
    result = await service.prune_images(node_id)
    return DockerPruneResponse(
        images_deleted=list(result.images_deleted),
        space_reclaimed=result.space_reclaimed,
    )
