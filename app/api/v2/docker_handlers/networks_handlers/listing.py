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


@router.get("/networks", response_model=CursorPage[DockerNetwork])
@inject
async def list_networks(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _key: Principal = Security(get_current_principal),
) -> CursorPage[DockerNetwork]:
    """List Docker networks with cursor pagination."""
    audit.info("api.v2.docker.networks.list", node_id=str(node_id))
    items = [
        DockerNetwork.model_validate(item, from_attributes=True)
        for item in await service.list_networks(node_id)
    ]
    sliced, next_cursor, has_more = paginate_offset(items, cursor, limit)
    return CursorPage[DockerNetwork](
        items=sliced, next_cursor=next_cursor, has_more=has_more, limit=limit
    )


@router.post(
    "/networks",
    response_model=DockerNetworkCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@inject
async def create_network(
    node_id: uuid.UUID,
    data: NetworkCreateRequest,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerNetworkCreateResponse:
    """Create a Docker network."""
    audit.info("api.v2.docker.networks.create", node_id=str(node_id), name=data.name)
    network_id = await service.create_network(
        NetworkCreateRequestDTO(
            node_id=node_id,
            name=data.name,
            driver=data.driver,
            subnet=data.subnet,
            gateway=data.gateway,
        )
    )
    return DockerNetworkCreateResponse(id=network_id, name=data.name)


@router.get("/networks/{network_id}", response_model=NetworkInspectResponse)
@inject
async def inspect_network(
    node_id: uuid.UUID,
    network_id: str,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(get_current_principal),
) -> NetworkInspectResponse:
    """Inspect a Docker network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.inspect",
        node_id=str(node_id),
        network_id=validated_id,
    )
    result = await service.inspect_network(node_id, validated_id)
    return NetworkInspectResponse(
        id=result.id,
        name=result.name,
        driver=result.driver,
        scope=result.scope,
        subnet=result.subnet,
        gateway=result.gateway,
        containers=[
            {
                "name": cdata.get("Name", cid),
                "ipv4_address": cdata.get("IPv4Address", ""),
            }
            for cid, cdata in result.containers
        ],
    )


@router.delete("/networks/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def remove_network(
    node_id: uuid.UUID,
    network_id: str,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a Docker network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.v2.docker.networks.remove",
        node_id=str(node_id),
        network_id=validated_id,
    )
    await service.remove_network(node_id, validated_id)


