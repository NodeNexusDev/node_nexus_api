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
    sliced, next_cursor, has_more = paginate_offset(items, cursor, limit)
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
