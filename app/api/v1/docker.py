"""Docker management HTTP adapter."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.core.docker_validation import validate_container_id
from app.schemas.docker import (
    DockerContainer,
    DockerContainerInspect,
    DockerExecRequest,
    DockerExecResult,
    DockerImage,
    DockerImagePullRequest,
    DockerNetwork,
    DockerPullResult,
    DockerStats,
    DockerVolume,
)
from app.services.docker.container_service import DockerContainerService
from app.services.docker.image_service import DockerImageService
from app.services.docker.resource_service import DockerResourceService

audit = structlog.get_logger("audit")
router = APIRouter(
    prefix="/nodes/{node_id}/docker", tags=["docker"], route_class=DishkaRoute
)


@router.get("/containers")
@inject
async def list_containers(
    node_id: uuid.UUID,
    service: FromDishka[DockerContainerService],
    all: bool = Query(False, description="Show stopped containers"),
    _key: str = Security(get_current_api_key),
) -> list[DockerContainer]:
    """List containers on a Docker node."""
    audit.info("api.docker.containers.list", node_id=str(node_id), all=all)
    return [
        DockerContainer.model_validate(item, from_attributes=True)
        for item in await service.list_containers(node_id, all=all)
    ]


@router.get("/containers/{container_id}")
@inject
async def get_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: str = Security(get_current_api_key),
) -> DockerContainerInspect:
    """Get container details."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.get", node_id=str(node_id), container_id=validated_id
    )
    result = await service.get_container(node_id, validated_id)
    return DockerContainerInspect.model_validate(result, from_attributes=True)


@router.post("/containers/{container_id}/start", status_code=204)
@inject
async def start_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: str = Security(require_write_scope),
) -> None:
    """Start a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.start", node_id=str(node_id), container_id=validated_id
    )
    await service.start_container(node_id, validated_id)


@router.post("/containers/{container_id}/stop", status_code=204)
@inject
async def stop_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    timeout: int = Query(10, ge=1, le=300),
    _key: str = Security(require_write_scope),
) -> None:
    """Stop a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.stop", node_id=str(node_id), container_id=validated_id
    )
    await service.stop_container(node_id, validated_id, timeout=timeout)


@router.post("/containers/{container_id}/restart", status_code=204)
@inject
async def restart_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    timeout: int = Query(10, ge=1, le=300),
    _key: str = Security(require_write_scope),
) -> None:
    """Restart a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.restart", node_id=str(node_id), container_id=validated_id
    )
    await service.restart_container(node_id, validated_id, timeout=timeout)


@router.delete("/containers/{container_id}", status_code=204)
@inject
async def remove_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    force: bool = Query(False),
    _key: str = Security(require_write_scope),
) -> None:
    """Remove a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.remove", node_id=str(node_id), container_id=validated_id
    )
    await service.remove_container(node_id, validated_id, force=force)


@router.get("/containers/{container_id}/logs")
@inject
async def get_logs(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    tail: int = Query(100, ge=1, le=10000),
    since: str | None = Query(None),
    _key: str = Security(get_current_api_key),
) -> str:
    """Get container logs."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.logs", node_id=str(node_id), container_id=validated_id
    )
    return await service.get_logs(node_id, validated_id, tail=tail, since=since)


@router.post("/containers/{container_id}/exec")
@inject
async def exec_command(
    node_id: uuid.UUID,
    container_id: str,
    data: DockerExecRequest,
    service: FromDishka[DockerContainerService],
    _key: str = Security(require_write_scope),
) -> DockerExecResult:
    """Execute a command in a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.exec",
        node_id=str(node_id),
        container_id=validated_id,
        command=data.command,
    )
    result = await service.exec_command(
        node_id, validated_id, data.command, timeout=data.timeout
    )
    return DockerExecResult.model_validate(result, from_attributes=True)


@router.get("/images")
@inject
async def list_images(
    node_id: uuid.UUID,
    service: FromDishka[DockerImageService],
    _key: str = Security(get_current_api_key),
) -> list[DockerImage]:
    """List images on a Docker node."""
    audit.info("api.docker.images.list", node_id=str(node_id))
    return [
        DockerImage.model_validate(item, from_attributes=True)
        for item in await service.list_images(node_id)
    ]


@router.post("/images/pull")
@inject
async def pull_image(
    node_id: uuid.UUID,
    data: DockerImagePullRequest,
    service: FromDishka[DockerImageService],
    _key: str = Security(require_write_scope),
) -> DockerPullResult:
    """Pull a Docker image."""
    audit.info("api.docker.images.pull", node_id=str(node_id), image=data.image)
    result = await service.pull_image(node_id, data.image, timeout=data.timeout)
    return DockerPullResult.model_validate(result, from_attributes=True)


@router.get("/containers/{container_id}/stats")
@inject
async def get_stats(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: str = Security(get_current_api_key),
) -> DockerStats:
    """Get container stats."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.stats", node_id=str(node_id), container_id=validated_id
    )
    result = await service.get_stats(node_id, validated_id)
    return DockerStats.model_validate(result, from_attributes=True)


@router.get("/networks")
@inject
async def list_networks(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: str = Security(get_current_api_key),
) -> list[DockerNetwork]:
    """List Docker networks."""
    audit.info("api.docker.networks.list", node_id=str(node_id))
    return [
        DockerNetwork.model_validate(item, from_attributes=True)
        for item in await service.list_networks(node_id)
    ]


@router.get("/volumes")
@inject
async def list_volumes(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: str = Security(get_current_api_key),
) -> list[DockerVolume]:
    """List Docker volumes."""
    audit.info("api.docker.volumes.list", node_id=str(node_id))
    return [
        DockerVolume.model_validate(item, from_attributes=True)
        for item in await service.list_volumes(node_id)
    ]
