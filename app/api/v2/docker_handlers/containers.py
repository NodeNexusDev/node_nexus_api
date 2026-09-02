# ruff: noqa: F401, I001
"""Docker management HTTP adapter v2 with cursor pagination and vert bulk."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Response, Security, status

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.api.pagination import decode_offset, encode_offset, paginate_offset
from app.api.v2._bulk import execute_vert_bulk
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
    ContainerBulkResult,
    ContainerCreatedResponse,
    ContainerCreateRequest,
    ContainerExecBulkResult,
    ContainerExecutionsRequest,
    ContainerIdsRequest,
    ContainerInspectBulkResult,
    ContainerInspectionsRequest,
    ContainerKillsRequest,
    ContainerLogsBulkResult,
    ContainerLogsRequest,
    ContainerRenameRequest,
    ContainerStatsBulkResult,
    ContainerStatsRequest,
    ContainerUpdatesRequest,
    DockerActionResponse,
    DockerArchiveResponse,
    DockerContainer,
    DockerContainerInspect,
    DockerContainerRenameResponse,
    DockerExecRequest,
    DockerExecResult,
    DockerImage,
    DockerImageBuildRequest,
    DockerImageBuildResponse,
    DockerImageHistoryItem,
    DockerImageHistoryResponse,
    DockerImageInspectResponse,
    DockerImagePullRequest,
    DockerImagePushRequest,
    DockerImageTagRequest,
    DockerImageTagResponse,
    DockerNetwork,
    DockerNetworkCreateResponse,
    DockerPortResponse,
    DockerPruneResponse,
    DockerPullResult,
    DockerStats,
    DockerSystemDfItem,
    DockerSystemInfo,
    DockerTopResult,
    DockerVersionResponse,
    DockerVolume,
    DockerVolumeCreateResponse,
    DockerVolumePruneResponse,
    DockerWaitResponse,
    ImageBulkResult,
    ImagePullsRequest,
    ImageRemovalsRequest,
    KillRequest,
    NetworkBulkResult,
    NetworkConnectRequest,
    NetworkCreateRequest,
    NetworkDisconnectRequest,
    NetworkInspectResponse,
    NetworkRemovalsRequest,
    UpdateRequest,
    VolumeBulkResult,
    VolumeCreateRequest,
    VolumeInspectResponse,
    VolumeRemovalsRequest,
)

audit = structlog.get_logger("audit")

# Compatibility aliases for tests importing private helpers
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816
_paginate_offset = paginate_offset  # noqa: N816
router = APIRouter(tags=["docker"], route_class=DishkaRoute)


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
    sliced, next_cursor, has_more = paginate_offset(items, cursor, limit)
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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


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

    return await execute_vert_bulk(data.container_ids, _one, response)


# ---------------------------------------------------------------------------
# Images — cursor pagination + single + bulk
# ---------------------------------------------------------------------------


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
