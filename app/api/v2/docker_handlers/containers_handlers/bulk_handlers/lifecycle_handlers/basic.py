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
