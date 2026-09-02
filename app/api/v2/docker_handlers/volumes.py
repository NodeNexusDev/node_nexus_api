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
    sliced, next_cursor, has_more = paginate_offset(items, cursor, limit)
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

    return await execute_vert_bulk(data.volume_names, _one, response)


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
