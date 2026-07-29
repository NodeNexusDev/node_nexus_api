"""Docker bulk operations API endpoints."""

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Security

from app.api.deps import require_write_scope
from app.schemas.docker import BulkDockerRequest, BulkDockerResponse
from app.services.docker.bulk_service import DockerBulkService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/docker", tags=["docker"], route_class=DishkaRoute)


def _bulk_response(result: object) -> BulkDockerResponse:
    return BulkDockerResponse.model_validate(result, from_attributes=True)


@router.post("/bulk/start")
@inject
async def bulk_start_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Start containers on multiple nodes."""
    audit.info("api.docker.bulk.start", node_count=len(data.node_ids))
    result = await service.bulk_container_action(
        node_ids=data.node_ids,
        container_id=data.container_id,
        action="start",
    )
    return _bulk_response(result)


@router.post("/bulk/stop")
@inject
async def bulk_stop_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Stop containers on multiple nodes."""
    audit.info("api.docker.bulk.stop", node_count=len(data.node_ids))
    result = await service.bulk_container_action(
        node_ids=data.node_ids,
        container_id=data.container_id,
        action="stop",
        timeout=data.timeout,
    )
    return _bulk_response(result)


@router.post("/bulk/restart")
@inject
async def bulk_restart_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Restart containers on multiple nodes."""
    audit.info("api.docker.bulk.restart", node_count=len(data.node_ids))
    result = await service.bulk_container_action(
        node_ids=data.node_ids,
        container_id=data.container_id,
        action="restart",
        timeout=data.timeout,
    )
    return _bulk_response(result)


@router.post("/bulk/exec")
@inject
async def bulk_exec_in_containers(
    data: BulkDockerRequest,
    service: FromDishka[DockerBulkService],
    _key: str = Security(require_write_scope),
) -> BulkDockerResponse:
    """Execute a command in containers on multiple nodes."""
    if not data.command:
        raise HTTPException(status_code=422, detail="command is required for exec")
    audit.info("api.docker.bulk.exec", node_count=len(data.node_ids))
    result = await service.bulk_exec(
        node_ids=data.node_ids,
        container_id=data.container_id,
        command=data.command,
        timeout=data.timeout or 30,
    )
    return _bulk_response(result)
