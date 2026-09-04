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


