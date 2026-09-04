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
