"""Docker bulk operations API endpoints."""

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Security

from app.api.deps import require_write_scope
from app.application.services.docker.bulk_service import DockerBulkService
from app.schemas.docker import (
    BulkDockerImageBuildRequest,
    BulkDockerImageBuildResponse,
    BulkDockerImageBuildResult,
    BulkDockerImageRemoveRequest,
    BulkDockerImageRemoveResponse,
    BulkDockerImageRemoveResult,
    BulkDockerPullRequest,
    BulkDockerPullResponse,
    BulkDockerPullResult,
    BulkDockerRequest,
    BulkDockerResponse,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/docker", tags=["docker"], route_class=DishkaRoute)


def _bulk_response(result: object) -> BulkDockerResponse:
    return BulkDockerResponse.model_validate(result, from_attributes=True)


@router.post("/bulk/start", response_model=BulkDockerResponse)
@inject
async def bulk_start_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Start containers on multiple nodes."""
    audit.info(
        "api.docker.bulk.start",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
    )
    result = await service.bulk_container_action(
        node_ids=data.node_ids,
        container_id=data.container_id,
        action="start",
        node_tags=data.node_tags,
    )
    return _bulk_response(result)


@router.post("/bulk/stop", response_model=BulkDockerResponse)
@inject
async def bulk_stop_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Stop containers on multiple nodes."""
    audit.info(
        "api.docker.bulk.stop",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
    )
    result = await service.bulk_container_action(
        node_ids=data.node_ids,
        container_id=data.container_id,
        action="stop",
        timeout=data.timeout,
        node_tags=data.node_tags,
    )
    return _bulk_response(result)


@router.post("/bulk/restart", response_model=BulkDockerResponse)
@inject
async def bulk_restart_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Restart containers on multiple nodes."""
    audit.info(
        "api.docker.bulk.restart",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
    )
    result = await service.bulk_container_action(
        node_ids=data.node_ids,
        container_id=data.container_id,
        action="restart",
        timeout=data.timeout,
        node_tags=data.node_tags,
    )
    return _bulk_response(result)


@router.post("/bulk/remove", response_model=BulkDockerResponse)
@inject
async def bulk_remove_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Remove containers on multiple nodes."""
    audit.info(
        "api.docker.bulk.remove",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
    )
    result = await service.bulk_container_action(
        node_ids=data.node_ids,
        container_id=data.container_id,
        action="remove",
        node_tags=data.node_tags,
    )
    return _bulk_response(result)


@router.post("/bulk/exec", response_model=BulkDockerResponse)
@inject
async def bulk_exec_in_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Execute a command in containers on multiple nodes."""
    if not data.command:
        raise HTTPException(status_code=422, detail="command is required for exec")
    audit.info(
        "api.docker.bulk.exec",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
    )
    result = await service.bulk_exec(
        node_ids=data.node_ids,
        container_id=data.container_id,
        command=data.command,
        timeout=data.timeout or 30,
        node_tags=data.node_tags,
    )
    return _bulk_response(result)


@router.post("/bulk/pull", response_model=BulkDockerPullResponse)
@inject
async def bulk_pull_images(
    data: BulkDockerPullRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerPullResponse:
    """Pull Docker images on multiple nodes."""
    audit.info(
        "api.docker.bulk.pull",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
        image=data.image,
    )
    dto = await service.bulk_pull_image(
        node_ids=data.node_ids,
        image=data.image,
        timeout=data.timeout,
        node_tags=data.node_tags,
    )
    return BulkDockerPullResponse(
        results=[
            BulkDockerPullResult(
                node_id=r.node_id,
                node_name=r.node_name,
                status=r.status,
                output=r.output,
                error=r.error,
            )
            for r in dto.results
        ],
        total=dto.total,
        succeeded=dto.succeeded,
        failed=dto.failed,
    )


@router.post("/bulk/images/remove", response_model=BulkDockerImageRemoveResponse)
@inject
async def bulk_remove_images(
    data: BulkDockerImageRemoveRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerImageRemoveResponse:
    """Remove Docker images on multiple nodes."""
    audit.info(
        "api.docker.bulk.images.remove",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
        image_id=data.image_id,
    )
    dto = await service.bulk_image_remove(
        node_ids=data.node_ids,
        image_id=data.image_id,
        node_tags=data.node_tags,
    )
    return BulkDockerImageRemoveResponse(
        results=[
            BulkDockerImageRemoveResult(
                node_id=r.node_id,
                node_name=r.node_name,
                status=r.status,
                output=r.output,
                error=r.error,
            )
            for r in dto.results
        ],
        total=dto.total,
        succeeded=dto.succeeded,
        failed=dto.failed,
    )


@router.post("/bulk/images/build", response_model=BulkDockerImageBuildResponse)
@inject
async def bulk_build_images(
    data: BulkDockerImageBuildRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerImageBuildResponse:
    """Build Docker images on multiple nodes."""
    audit.info(
        "api.docker.bulk.images.build",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
        tag=data.tag,
    )
    dto = await service.bulk_image_build(
        node_ids=data.node_ids,
        dockerfile=data.dockerfile,
        tag=data.tag,
        build_args=data.build_args,
        no_cache=data.no_cache,
        timeout=data.timeout,
        node_tags=data.node_tags,
    )
    return BulkDockerImageBuildResponse(
        results=[
            BulkDockerImageBuildResult(
                node_id=r.node_id,
                node_name=r.node_name,
                status=r.status,
                output=r.output,
                error=r.error,
            )
            for r in dto.results
        ],
        total=dto.total,
        succeeded=dto.succeeded,
        failed=dto.failed,
    )


# ── Bulk inspect / logs / stats ────────────────────────────────────────────


@router.post("/bulk/inspect", response_model=BulkDockerResponse)
@inject
async def bulk_inspect_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Inspect a container on multiple nodes."""
    audit.info(
        "api.docker.bulk.inspect",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
        container_id=data.container_id,
    )
    result = await service.bulk_inspect(
        node_ids=data.node_ids,
        container_id=data.container_id,
        node_tags=data.node_tags,
    )
    return _bulk_response(result)


@router.post("/bulk/logs", response_model=BulkDockerResponse)
@inject
async def bulk_logs_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Get logs from a container on multiple nodes."""
    audit.info(
        "api.docker.bulk.logs",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
        container_id=data.container_id,
    )
    result = await service.bulk_logs(
        node_ids=data.node_ids,
        container_id=data.container_id,
        node_tags=data.node_tags,
    )
    return _bulk_response(result)


@router.post("/bulk/stats", response_model=BulkDockerResponse)
@inject
async def bulk_stats_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Get stats from a container on multiple nodes."""
    audit.info(
        "api.docker.bulk.stats",
        node_count=len(data.node_ids),
        node_tag_count=len(data.node_tags),
        container_id=data.container_id,
    )
    result = await service.bulk_stats(
        node_ids=data.node_ids,
        container_id=data.container_id,
        node_tags=data.node_tags,
    )
    return _bulk_response(result)
