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
router = APIRouter(route_class=DishkaRoute)


# ---------------------------------------------------------------------------
# Containers — create & lists with cursor pagination
# ---------------------------------------------------------------------------


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


