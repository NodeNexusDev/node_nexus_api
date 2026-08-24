"""Docker management HTTP adapter."""

import uuid
from dataclasses import asdict

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security, status

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.docker import (
    ContainerCreateRequestDTO,
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
from app.core.docker_validation import validate_container_id, validate_volume_name
from app.schemas.docker import (
    ContainerCreatedResponse,
    ContainerCreateRequest,
    DockerContainer,
    DockerContainerInspect,
    DockerExecRequest,
    DockerExecResult,
    DockerImage,
    DockerImageBuildRequest,
    DockerImageBuildResponse,
    DockerImageInspectResponse,
    DockerImagePullRequest,
    DockerImageTagRequest,
    DockerImageTagResponse,
    DockerNetwork,
    DockerPullResult,
    DockerStats,
    DockerVolume,
    NetworkConnectRequest,
    NetworkCreateRequest,
    NetworkDisconnectRequest,
    NetworkInspectResponse,
    VolumeCreateRequest,
    VolumeInspectResponse,
)

audit = structlog.get_logger("audit")
router = APIRouter(
    prefix="/nodes/{node_id}/docker", tags=["docker"], route_class=DishkaRoute
)


@router.post("/containers", status_code=status.HTTP_201_CREATED)
@inject
async def create_container(
    node_id: uuid.UUID,
    data: ContainerCreateRequest,
    service: FromDishka[DockerContainerService],
    _key: str = Security(require_write_scope),
) -> ContainerCreatedResponse:
    """Create a container on a Docker node via ``docker create``."""
    audit.info(
        "api.docker.containers.create",
        node_id=str(node_id),
        image=data.image,
        name=data.name,
    )
    request = ContainerCreateRequestDTO(
        node_id=node_id,
        image=data.image,
        name=data.name,
        command=data.command,
        ports=tuple(data.ports.items()),
        volumes=tuple((hp, m.bind, m.mode) for hp, m in data.volumes.items()),
        env=tuple(data.env),
        labels=tuple(data.labels.items()),
        network=data.network,
        restart_policy=data.restart_policy,
    )
    result = await service.create_container(request)
    return ContainerCreatedResponse.model_validate(result, from_attributes=True)


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
    payload = asdict(result)
    payload["network_settings"] = dict(result.network_settings)
    return DockerContainerInspect.model_validate(payload)


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


@router.post("/images/build")
@inject
async def build_image(
    node_id: uuid.UUID,
    data: DockerImageBuildRequest,
    service: FromDishka[DockerImageService],
    _key: str = Security(require_write_scope),
) -> DockerImageBuildResponse:
    """Build a Docker image from a Dockerfile piped through stdin."""
    audit.info(
        "api.docker.images.build",
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


@router.get("/images/{image_id:path}")
@inject
async def inspect_image(
    node_id: uuid.UUID,
    image_id: str,
    service: FromDishka[DockerImageService],
    _key: str = Security(get_current_api_key),
) -> DockerImageInspectResponse:
    """Inspect a Docker image."""
    audit.info("api.docker.images.inspect", node_id=str(node_id), image_id=image_id)
    result = await service.inspect_image(node_id, image_id)
    return DockerImageInspectResponse.model_validate(result, from_attributes=True)


@router.delete("/images/{image_id:path}", status_code=204)
@inject
async def remove_image(
    node_id: uuid.UUID,
    image_id: str,
    service: FromDishka[DockerImageService],
    _key: str = Security(require_write_scope),
) -> None:
    """Remove a Docker image."""
    audit.info("api.docker.images.remove", node_id=str(node_id), image_id=image_id)
    await service.remove_image(node_id, image_id)


@router.post("/images/{image_id:path}/tag")
@inject
async def tag_image(
    node_id: uuid.UUID,
    image_id: str,
    data: DockerImageTagRequest,
    service: FromDishka[DockerImageService],
    _key: str = Security(require_write_scope),
) -> DockerImageTagResponse:
    """Tag a Docker image."""
    audit.info(
        "api.docker.images.tag",
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


# ── Network CRUD ────────────────────────────────────────────────────────────


@router.post("/networks", status_code=status.HTTP_201_CREATED)
@inject
async def create_network(
    node_id: uuid.UUID,
    data: NetworkCreateRequest,
    service: FromDishka[DockerResourceService],
    _key: str = Security(require_write_scope),
) -> dict[str, str]:
    """Create a Docker network."""
    audit.info("api.docker.networks.create", node_id=str(node_id), name=data.name)
    network_id = await service.create_network(
        NetworkCreateRequestDTO(
            node_id=node_id,
            name=data.name,
            driver=data.driver,
            subnet=data.subnet,
            gateway=data.gateway,
        )
    )
    return {"id": network_id, "name": data.name}


@router.get("/networks/{network_id}")
@inject
async def inspect_network(
    node_id: uuid.UUID,
    network_id: str,
    service: FromDishka[DockerResourceService],
    _key: str = Security(get_current_api_key),
) -> NetworkInspectResponse:
    """Inspect a Docker network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.docker.networks.inspect",
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
    _key: str = Security(require_write_scope),
) -> None:
    """Remove a Docker network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.docker.networks.remove",
        node_id=str(node_id),
        network_id=validated_id,
    )
    await service.remove_network(node_id, validated_id)


@router.post("/networks/{network_id}/connect")
@inject
async def connect_to_network(
    node_id: uuid.UUID,
    network_id: str,
    data: NetworkConnectRequest,
    service: FromDishka[DockerResourceService],
    _key: str = Security(require_write_scope),
) -> dict[str, str]:
    """Connect a container to a network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.docker.networks.connect",
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
    return {"status": "connected"}


@router.post("/networks/{network_id}/disconnect")
@inject
async def disconnect_from_network(
    node_id: uuid.UUID,
    network_id: str,
    data: NetworkDisconnectRequest,
    service: FromDishka[DockerResourceService],
    _key: str = Security(require_write_scope),
) -> dict[str, str]:
    """Disconnect a container from a network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.docker.networks.disconnect",
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
    return {"status": "disconnected"}


# ── Volume CRUD ─────────────────────────────────────────────────────────────


@router.post("/volumes", status_code=status.HTTP_201_CREATED)
@inject
async def create_volume(
    node_id: uuid.UUID,
    data: VolumeCreateRequest,
    service: FromDishka[DockerResourceService],
    _key: str = Security(require_write_scope),
) -> dict[str, str]:
    """Create a Docker volume."""
    audit.info("api.docker.volumes.create", node_id=str(node_id))
    volume_name = await service.create_volume(
        VolumeCreateRequestDTO(
            node_id=node_id,
            name=data.name,
            driver=data.driver,
        )
    )
    return {"name": volume_name}


@router.get("/volumes/{volume_name}")
@inject
async def inspect_volume(
    node_id: uuid.UUID,
    volume_name: str,
    service: FromDishka[DockerResourceService],
    _key: str = Security(get_current_api_key),
) -> VolumeInspectResponse:
    """Inspect a Docker volume."""
    validated_name = validate_volume_name(volume_name)
    audit.info("api.docker.volumes.inspect", node_id=str(node_id), name=validated_name)
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
    _key: str = Security(require_write_scope),
) -> None:
    """Remove a Docker volume."""
    validated_name = validate_volume_name(volume_name)
    audit.info("api.docker.volumes.remove", node_id=str(node_id), name=validated_name)
    await service.remove_volume(node_id, validated_name)


@router.post("/volumes/prune")
@inject
async def prune_volumes(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: str = Security(require_write_scope),
) -> dict[str, str]:
    """Prune unused Docker volumes."""
    audit.info("api.docker.volumes.prune", node_id=str(node_id))
    output = await service.prune_volumes(node_id)
    return {"output": output}
