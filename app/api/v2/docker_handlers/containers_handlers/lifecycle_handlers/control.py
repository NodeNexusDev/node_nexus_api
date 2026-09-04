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
