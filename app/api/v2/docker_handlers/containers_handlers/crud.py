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


