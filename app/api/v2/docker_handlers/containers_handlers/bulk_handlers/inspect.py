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
    "/containers/executions", response_model=BulkResult[ContainerExecBulkResult]
)
@inject
async def bulk_executions(
    node_id: uuid.UUID,
    data: ContainerExecutionsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ContainerExecBulkResult]:
    """Execute a command in multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.executions",
        node_id=str(node_id),
        count=len(data.container_ids),
        command_fingerprint=command_fingerprint(data.command),
    )

    async def _one(cid: str) -> ContainerExecBulkResult:
        try:
            validated = validate_container_id(cid)
            res = await service.exec_command(
                node_id, validated, data.command, timeout=data.timeout
            )
            st: Literal["success", "error"] = (
                "success" if res.exit_code == 0 else "error"
            )
            return ContainerExecBulkResult(
                container_id=cid,
                status=st,
                stdout=res.stdout,
                stderr=res.stderr,
                exit_code=res.exit_code,
                error="" if st == "success" else res.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerExecBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    return await execute_vert_bulk(data.container_ids, _one, response)


@router.post(
    "/containers/inspections", response_model=BulkResult[ContainerInspectBulkResult]
)
@inject
async def bulk_inspections(
    node_id: uuid.UUID,
    data: ContainerInspectionsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(get_current_principal),
) -> BulkResult[ContainerInspectBulkResult]:
    """Inspect multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.inspections",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerInspectBulkResult:
        try:
            validated = validate_container_id(cid)
            res = await service.get_container(node_id, validated)
            payload = asdict(res)
            payload["network_settings"] = dict(res.network_settings)
            insp = DockerContainerInspect.model_validate(payload)
            return ContainerInspectBulkResult(
                container_id=cid, status="success", data=insp
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerInspectBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    return await execute_vert_bulk(data.container_ids, _one, response)


@router.post("/containers/logs", response_model=BulkResult[ContainerLogsBulkResult])
@inject
async def bulk_logs(
    node_id: uuid.UUID,
    data: ContainerLogsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(get_current_principal),
) -> BulkResult[ContainerLogsBulkResult]:
    """Get logs from multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.logs.bulk",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerLogsBulkResult:
        try:
            validated = validate_container_id(cid)
            logs = await service.get_logs(
                node_id, validated, tail=data.tail, since=data.since
            )
            return ContainerLogsBulkResult(
                container_id=cid, status="success", logs=logs
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerLogsBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    return await execute_vert_bulk(data.container_ids, _one, response)


@router.post("/containers/stats", response_model=BulkResult[ContainerStatsBulkResult])
@inject
async def bulk_stats(
    node_id: uuid.UUID,
    data: ContainerStatsRequest,
    service: FromDishka[DockerContainerService],
    response: Response,
    _key: Principal = Security(get_current_principal),
) -> BulkResult[ContainerStatsBulkResult]:
    """Get stats from multiple containers (vert bulk, 207)."""
    audit.info(
        "api.v2.docker.containers.stats.bulk",
        node_id=str(node_id),
        count=len(data.container_ids),
    )

    async def _one(cid: str) -> ContainerStatsBulkResult:
        try:
            validated = validate_container_id(cid)
            res = await service.get_stats(node_id, validated)
            stats = DockerStats.model_validate(res, from_attributes=True)
            return ContainerStatsBulkResult(
                container_id=cid, status="success", stats=stats
            )
        except Exception as exc:  # noqa: BLE001
            return ContainerStatsBulkResult(
                container_id=cid, status="error", error=str(exc)
            )

    return await execute_vert_bulk(data.container_ids, _one, response)


# ---------------------------------------------------------------------------
# Images — cursor pagination + single + bulk
# ---------------------------------------------------------------------------


