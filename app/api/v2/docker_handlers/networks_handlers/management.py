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


@router.post("/networks/removals", response_model=BulkResult[NetworkBulkResult])
@inject
async def bulk_network_removals(
    node_id: uuid.UUID,
    data: NetworkRemovalsRequest,
    service: FromDishka[DockerResourceService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[NetworkBulkResult]:
    """Remove multiple networks (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.networks.removals",
        node_id=str(node_id),
        count=len(data.network_ids),
    )

    async def _one(nid: str) -> NetworkBulkResult:
        try:
            validated = validate_container_id(nid)
            await service.remove_network(node_id, validated)
            return NetworkBulkResult(network_id=nid, status="success")
        except Exception as exc:  # noqa: BLE001
            return NetworkBulkResult(network_id=nid, status="error", error=str(exc))

    return await execute_vert_bulk(data.network_ids, _one, response)


@router.post("/networks/prune", response_model=DockerVolumePruneResponse)
@inject
async def prune_networks(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerVolumePruneResponse:
    """Prune unused Docker networks."""
    audit.info("api.v2.docker.networks.prune", node_id=str(node_id))
    output = await service.prune_networks(node_id)
    return DockerVolumePruneResponse(output=output)


@router.post("/networks/{network_id}/connect", response_model=DockerActionResponse)
@inject
async def connect_to_network(
    node_id: uuid.UUID,
    network_id: str,
    data: NetworkConnectRequest,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Connect a container to a network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.connect",
        node_id=str(node_id),
        network_id=validated_id,
        container_id=data.container_id,
    )
    await service.connect_to_network(
        NetworkConnectRequestDTO(
            node_id=node_id,
            network_id=validated_id,
            container_id=data.container_id,
            ip_address=data.ip_address,
        )
    )
    return DockerActionResponse(status="connected")


@router.post("/networks/{network_id}/disconnect", response_model=DockerActionResponse)
@inject
async def disconnect_from_network(
    node_id: uuid.UUID,
    network_id: str,
    data: NetworkDisconnectRequest,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Disconnect a container from a network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.disconnect",
        node_id=str(node_id),
        network_id=validated_id,
        container_id=data.container_id,
    )
    await service.disconnect_from_network(
        NetworkDisconnectRequestDTO(
            node_id=node_id,
            network_id=validated_id,
            container_id=data.container_id,
            force=data.force,
        )
    )
    return DockerActionResponse(status="disconnected")


# ---------------------------------------------------------------------------
# Volumes — cursor pagination + CRUD + bulk + prune
# ---------------------------------------------------------------------------
