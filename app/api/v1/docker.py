"""Docker management HTTP adapter."""

import uuid
from dataclasses import asdict

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security, status

from app.api.deps import (
    Principal,
    get_current_principal,
    require_write_or_jwt_scope,
)
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
from app.schemas.docker import (
    ContainerCreatedResponse,
    ContainerCreateRequest,
    ContainerRenameRequest,
    DockerActionResponse,
    DockerContainer,
    DockerContainerInspect,
    DockerContainerRenameResponse,
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
    DockerNetworkCreateResponse,
    DockerPruneResponse,
    DockerPullResult,
    DockerStats,
    DockerSystemDfItem,
    DockerSystemInfo,
    DockerTopResult,
    DockerVolume,
    DockerVolumeCreateResponse,
    DockerVolumePruneResponse,
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


@router.post(
    "/containers",
    response_model=ContainerCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
@inject
async def create_container(
    node_id: uuid.UUID,
    data: ContainerCreateRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
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


@router.get("/containers", response_model=list[DockerContainer])
@inject
async def list_containers(
    node_id: uuid.UUID,
    service: FromDishka[DockerContainerService],
    all: bool = Query(False, description="Show stopped containers"),
    _key: Principal = Security(get_current_principal),
) -> list[DockerContainer]:
    """List containers on a Docker node."""
    audit.info("api.docker.containers.list", node_id=str(node_id), all=all)
    return [
        DockerContainer.model_validate(item, from_attributes=True)
        for item in await service.list_containers(node_id, all=all)
    ]


@router.get("/containers/{container_id}", response_model=DockerContainerInspect)
@inject
async def get_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(get_current_principal),
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
    _key: Principal = Security(require_write_or_jwt_scope),
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
    _key: Principal = Security(require_write_or_jwt_scope),
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
    _key: Principal = Security(require_write_or_jwt_scope),
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
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.remove", node_id=str(node_id), container_id=validated_id
    )
    await service.remove_container(node_id, validated_id, force=force)


@router.get("/containers/{container_id}/logs", response_model=str)
@inject
async def get_logs(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    tail: int = Query(100, ge=1, le=10000),
    since: str | None = Query(None),
    _key: Principal = Security(get_current_principal),
) -> str:
    """Get container logs."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.logs", node_id=str(node_id), container_id=validated_id
    )
    return await service.get_logs(node_id, validated_id, tail=tail, since=since)


@router.post("/containers/{container_id}/exec", response_model=DockerExecResult)
@inject
async def exec_command(
    node_id: uuid.UUID,
    container_id: str,
    data: DockerExecRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerExecResult:
    """Execute a command in a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.exec",
        node_id=str(node_id),
        container_id=validated_id,
        command_fingerprint=command_fingerprint(data.command),
        command_length=len(data.command),
    )
    result = await service.exec_command(
        node_id, validated_id, data.command, timeout=data.timeout
    )
    return DockerExecResult.model_validate(result, from_attributes=True)


# ── Container lifecycle extensions ──────────────────────────────────────────


@router.post("/containers/{container_id}/pause", response_model=DockerActionResponse)
@inject
async def pause_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Pause a running container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.pause",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.pause_container(node_id, validated_id)
    return DockerActionResponse(status="paused")


@router.post("/containers/{container_id}/unpause", response_model=DockerActionResponse)
@inject
async def unpause_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerActionResponse:
    """Unpause a paused container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.unpause",
        node_id=str(node_id),
        container_id=validated_id,
    )
    await service.unpause_container(node_id, validated_id)
    return DockerActionResponse(status="unpaused")


@router.post(
    "/containers/{container_id}/rename",
    response_model=DockerContainerRenameResponse,
)
@inject
async def rename_container(
    node_id: uuid.UUID,
    container_id: str,
    data: ContainerRenameRequest,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerContainerRenameResponse:
    """Rename a container."""
    validated_id = validate_container_id(container_id)
    new_name = validate_container_new_name(data.new_name)
    audit.info(
        "api.docker.containers.rename",
        node_id=str(node_id),
        container_id=validated_id,
        new_name=new_name,
    )
    await service.rename_container(
        ContainerRenameRequestDTO(
            node_id=node_id,
            container_id=validated_id,
            new_name=new_name,
        )
    )
    return DockerContainerRenameResponse(status="renamed", new_name=new_name)


@router.get("/containers/{container_id}/top", response_model=DockerTopResult)
@inject
async def top_container(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(get_current_principal),
) -> DockerTopResult:
    """List processes running inside a container."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.top",
        node_id=str(node_id),
        container_id=validated_id,
    )
    result = await service.top_container(node_id, validated_id)
    return DockerTopResult(
        titles=result.titles,
        processes=[list(p) for p in result.processes],
    )


@router.get("/images", response_model=list[DockerImage])
@inject
async def list_images(
    node_id: uuid.UUID,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(get_current_principal),
) -> list[DockerImage]:
    """List images on a Docker node."""
    audit.info("api.docker.images.list", node_id=str(node_id))
    return [
        DockerImage.model_validate(item, from_attributes=True)
        for item in await service.list_images(node_id)
    ]


@router.post("/images/pull", response_model=DockerPullResult)
@inject
async def pull_image(
    node_id: uuid.UUID,
    data: DockerImagePullRequest,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPullResult:
    """Pull a Docker image."""
    audit.info("api.docker.images.pull", node_id=str(node_id), image=data.image)
    result = await service.pull_image(node_id, data.image, timeout=data.timeout)
    return DockerPullResult.model_validate(result, from_attributes=True)


@router.post("/images/build", response_model=DockerImageBuildResponse)
@inject
async def build_image(
    node_id: uuid.UUID,
    data: DockerImageBuildRequest,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(require_write_or_jwt_scope),
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


@router.get("/images/{image_id:path}", response_model=DockerImageInspectResponse)
@inject
async def inspect_image(
    node_id: uuid.UUID,
    image_id: str,
    service: FromDishka[DockerImageService],
    _key: Principal = Security(get_current_principal),
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
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a Docker image."""
    audit.info("api.docker.images.remove", node_id=str(node_id), image_id=image_id)
    await service.remove_image(node_id, image_id)


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


@router.get("/containers/{container_id}/stats", response_model=DockerStats)
@inject
async def get_stats(
    node_id: uuid.UUID,
    container_id: str,
    service: FromDishka[DockerContainerService],
    _key: Principal = Security(get_current_principal),
) -> DockerStats:
    """Get container stats."""
    validated_id = validate_container_id(container_id)
    audit.info(
        "api.docker.containers.stats", node_id=str(node_id), container_id=validated_id
    )
    result = await service.get_stats(node_id, validated_id)
    return DockerStats.model_validate(result, from_attributes=True)


@router.get("/networks", response_model=list[DockerNetwork])
@inject
async def list_networks(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(get_current_principal),
) -> list[DockerNetwork]:
    """List Docker networks."""
    audit.info("api.docker.networks.list", node_id=str(node_id))
    return [
        DockerNetwork.model_validate(item, from_attributes=True)
        for item in await service.list_networks(node_id)
    ]


@router.get("/volumes", response_model=list[DockerVolume])
@inject
async def list_volumes(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(get_current_principal),
) -> list[DockerVolume]:
    """List Docker volumes."""
    audit.info("api.docker.volumes.list", node_id=str(node_id))
    return [
        DockerVolume.model_validate(item, from_attributes=True)
        for item in await service.list_volumes(node_id)
    ]


# ── Network CRUD ────────────────────────────────────────────────────────────


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
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a Docker network."""
    validated_id = validate_container_id(network_id)
    audit.info(
        "api.docker.networks.remove",
        node_id=str(node_id),
        network_id=validated_id,
    )
    await service.remove_network(node_id, validated_id)


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
    return DockerActionResponse(status="disconnected")


# ── Volume CRUD ─────────────────────────────────────────────────────────────


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
    audit.info("api.docker.volumes.create", node_id=str(node_id))
    volume_name = await service.create_volume(
        VolumeCreateRequestDTO(
            node_id=node_id,
            name=data.name,
            driver=data.driver,
        )
    )
    return DockerVolumeCreateResponse(name=volume_name)


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
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a Docker volume."""
    validated_name = validate_volume_name(volume_name)
    audit.info("api.docker.volumes.remove", node_id=str(node_id), name=validated_name)
    await service.remove_volume(node_id, validated_name)


@router.post("/volumes/prune", response_model=DockerVolumePruneResponse)
@inject
async def prune_volumes(
    node_id: uuid.UUID,
    service: FromDishka[DockerResourceService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerVolumePruneResponse:
    """Prune unused Docker volumes."""
    audit.info("api.docker.volumes.prune", node_id=str(node_id))
    output = await service.prune_volumes(node_id)
    return DockerVolumePruneResponse(output=output)


# ── System ──────────────────────────────────────────────────────────────────


@router.get("/system/info", response_model=DockerSystemInfo)
@inject
async def system_info(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(get_current_principal),
) -> DockerSystemInfo:
    """Return Docker system information."""
    audit.info("api.docker.system.info", node_id=str(node_id))
    result = await service.info(node_id)
    return DockerSystemInfo.model_validate(result, from_attributes=True)


@router.get("/system/df", response_model=list[DockerSystemDfItem])
@inject
async def system_df(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(get_current_principal),
) -> list[DockerSystemDfItem]:
    """Return Docker disk usage."""
    audit.info("api.docker.system.df", node_id=str(node_id))
    results = await service.disk_usage(node_id)
    return [DockerSystemDfItem.model_validate(r, from_attributes=True) for r in results]


@router.post("/containers/prune", response_model=DockerPruneResponse)
@inject
async def prune_containers(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPruneResponse:
    """Prune stopped containers."""
    audit.info("api.docker.containers.prune", node_id=str(node_id))
    result = await service.prune_containers(node_id)
    return DockerPruneResponse(
        containers_deleted=list(result.containers_deleted),
        space_reclaimed=result.space_reclaimed,
    )


@router.post("/images/prune", response_model=DockerPruneResponse)
@inject
async def prune_images(
    node_id: uuid.UUID,
    service: FromDishka[DockerSystemService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> DockerPruneResponse:
    """Prune unused images."""
    audit.info("api.docker.images.prune", node_id=str(node_id))
    result = await service.prune_images(node_id)
    return DockerPruneResponse(
        images_deleted=list(result.images_deleted),
        space_reclaimed=result.space_reclaimed,
    )
