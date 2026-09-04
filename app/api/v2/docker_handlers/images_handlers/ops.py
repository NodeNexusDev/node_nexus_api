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

    return await execute_vert_bulk(data.images, _one, response)


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

    return await execute_vert_bulk(data.image_ids, _one, response)


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


