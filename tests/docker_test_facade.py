"""Test-only composition facade for focused Docker application services."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID

from app.application.dto.value_objects import NodeCredentials, NodeEndpoint

if TYPE_CHECKING:
    from app.adapters.persistence.dao.node import NodeRepository
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.docker_runtime import DockerRuntime
    from app.application.ports.node_reader import NodeConnectionReader
    from app.application.ports.remote_command import RemoteConnectorFactory

from app.adapters.runtime.docker import SshDockerRuntime
from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.docker import (
    BulkDockerResultDTO,
    ContainerRenameRequestDTO,
    DockerContainerDTO,
    DockerContainerInspectDTO,
    DockerExecResultDTO,
    DockerImageDTO,
    DockerNetworkDTO,
    DockerNetworkInspectDTO,
    DockerPruneResultDTO,
    DockerPullResultDTO,
    DockerStatsDTO,
    DockerSystemDfDTO,
    DockerSystemInfoDTO,
    DockerTopResultDTO,
    DockerVolumeDTO,
    DockerVolumeInspectDTO,
    NetworkConnectRequestDTO,
    NetworkCreateRequestDTO,
    NetworkDisconnectRequestDTO,
    VolumeCreateRequestDTO,
)
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.services.docker.bulk_service import DockerBulkService
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.application.services.docker.image_service import DockerImageService
from app.application.services.docker.parsers import parse_json_array, parse_json_lines
from app.application.services.docker.resource_service import DockerResourceService
from app.core.types import ConnectionType, JsonObject
from app.models.node import NodeModel


class DockerService:
    """Stable facade delegating to focused Docker domain services."""

    def __init__(
        self,
        repository: NodeRepository,
        audit_service: AuditEventSink | None = None,
        connector_factory: RemoteConnectorFactory | None = None,
        node_reader: NodeConnectionReader | None = None,
        runtime: DockerRuntime | None = None,
    ) -> None:
        self._audit = audit_service
        resolved_reader: NodeConnectionReader = (
            node_reader
            if node_reader is not None
            else _RepositoryNodeReader(repository)
        )
        resolved_runtime = runtime
        if resolved_runtime is None:
            if connector_factory is None:
                raise RuntimeError("DockerRuntime not configured")
            resolved_runtime = SshDockerRuntime(
                connector_factory,
                AesGcmCredentialCipher(),
            )
        self._runner = DockerCommandRunner(
            node_reader=resolved_reader,
            runtime=resolved_runtime,
        )
        self._containers = DockerContainerService(self._runner, audit_service)
        self._images = DockerImageService(self._runner, audit_service)
        self._resources = DockerResourceService(self._runner, audit_service)
        self._bulk = DockerBulkService(self._runner)

    async def _log(
        self,
        action: str,
        node_id: UUID | None = None,
        details: JsonObject | None = None,
    ) -> None:
        """Compatibility audit hook for internal callers."""
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    # Private compatibility methods retained for existing internal callers/tests.
    async def _get_docker_node(self, node_id: UUID) -> NodeConnectionDTO:
        return await self._runner.get_target(node_id)

    async def _execute_docker_cmd(
        self, node: NodeConnectionDTO, command: str, timeout: int = 30
    ) -> tuple[str, str, int]:
        return await self._runner.execute(node, command, timeout)

    def _build_docker_cmd(self, node: NodeConnectionDTO, docker_args: str) -> str:
        return self._runner.build_command(node, docker_args)

    @staticmethod
    def _parse_json_lines(stdout: str) -> list[dict[str, object]]:
        return parse_json_lines(stdout)

    @staticmethod
    def _parse_json_array(stdout: str) -> list[dict[str, object]]:
        return parse_json_array(stdout)

    @staticmethod
    def _map_docker_error(stderr: str, exit_code: int) -> None:
        raise_for_docker_error(stderr, exit_code)

    async def list_containers(
        self, node_id: UUID, *, all: bool = False
    ) -> list[DockerContainerDTO]:
        return await self._containers.list_containers(node_id, all=all)

    async def get_container(
        self, node_id: UUID, container_id: str
    ) -> DockerContainerInspectDTO:
        return await self._containers.get_container(node_id, container_id)

    async def start_container(self, node_id: UUID, container_id: str) -> None:
        await self._containers.start_container(node_id, container_id)

    async def stop_container(
        self, node_id: UUID, container_id: str, *, timeout: int = 10
    ) -> None:
        await self._containers.stop_container(node_id, container_id, timeout=timeout)

    async def restart_container(
        self, node_id: UUID, container_id: str, *, timeout: int = 10
    ) -> None:
        await self._containers.restart_container(node_id, container_id, timeout=timeout)

    async def remove_container(
        self, node_id: UUID, container_id: str, *, force: bool = False
    ) -> None:
        await self._containers.remove_container(node_id, container_id, force=force)

    async def get_logs(
        self,
        node_id: UUID,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
    ) -> str:
        return await self._containers.get_logs(
            node_id, container_id, tail=tail, since=since
        )

    async def exec_command(
        self,
        node_id: UUID,
        container_id: str,
        command: str,
        *,
        timeout: int = 30,
    ) -> DockerExecResultDTO:
        return await self._containers.exec_command(
            node_id, container_id, command, timeout=timeout
        )

    async def get_stats(self, node_id: UUID, container_id: str) -> DockerStatsDTO:
        return await self._containers.get_stats(node_id, container_id)

    async def list_images(self, node_id: UUID) -> list[DockerImageDTO]:
        return await self._images.list_images(node_id)

    async def pull_image(
        self, node_id: UUID, image: str, *, timeout: int = 300
    ) -> DockerPullResultDTO:
        return await self._images.pull_image(node_id, image, timeout=timeout)

    async def list_networks(self, node_id: UUID) -> list[DockerNetworkDTO]:
        return await self._resources.list_networks(node_id)

    async def list_volumes(self, node_id: UUID) -> list[DockerVolumeDTO]:
        return await self._resources.list_volumes(node_id)

    # ── Network CRUD ────────────────────────────────────────────────────────

    async def create_network(self, data: NetworkCreateRequestDTO) -> str:
        return await self._resources.create_network(data)

    async def inspect_network(
        self, node_id: UUID, network_id: str
    ) -> DockerNetworkInspectDTO:
        return await self._resources.inspect_network(node_id, network_id)

    async def remove_network(self, node_id: UUID, network_id: str) -> None:
        await self._resources.remove_network(node_id, network_id)

    async def connect_to_network(self, data: NetworkConnectRequestDTO) -> None:
        await self._resources.connect_to_network(data)

    async def disconnect_from_network(self, data: NetworkDisconnectRequestDTO) -> None:
        await self._resources.disconnect_from_network(data)

    # ── Volume CRUD ─────────────────────────────────────────────────────────

    async def create_volume(self, data: VolumeCreateRequestDTO) -> str:
        return await self._resources.create_volume(data)

    async def inspect_volume(
        self, node_id: UUID, volume_name: str
    ) -> DockerVolumeInspectDTO:
        return await self._resources.inspect_volume(node_id, volume_name)

    async def remove_volume(self, node_id: UUID, volume_name: str) -> None:
        await self._resources.remove_volume(node_id, volume_name)

    async def prune_volumes(self, node_id: UUID) -> str:
        return await self._resources.prune_volumes(node_id)

    # ── Container lifecycle extensions ──────────────────────────────────────

    async def pause_container(self, node_id: UUID, container_id: str) -> None:
        await self._containers.pause_container(node_id, container_id)

    async def unpause_container(self, node_id: UUID, container_id: str) -> None:
        await self._containers.unpause_container(node_id, container_id)

    async def rename_container(self, data: ContainerRenameRequestDTO) -> None:
        await self._containers.rename_container(data)

    async def top_container(
        self, node_id: UUID, container_id: str
    ) -> DockerTopResultDTO:
        return await self._containers.top_container(node_id, container_id)

    # ── System operations ───────────────────────────────────────────────────

    async def info(self, node_id: UUID) -> DockerSystemInfoDTO:
        from app.application.services.docker.system_service import DockerSystemService

        system = DockerSystemService(self._runner)
        return await system.info(node_id)

    async def disk_usage(self, node_id: UUID) -> list[DockerSystemDfDTO]:
        from app.application.services.docker.system_service import DockerSystemService

        system = DockerSystemService(self._runner)
        return await system.disk_usage(node_id)

    async def prune_containers(self, node_id: UUID) -> DockerPruneResultDTO:
        from app.application.services.docker.system_service import DockerSystemService

        system = DockerSystemService(self._runner)
        return await system.prune_containers(node_id)

    async def prune_images(self, node_id: UUID) -> DockerPruneResultDTO:
        from app.application.services.docker.system_service import DockerSystemService

        system = DockerSystemService(self._runner)
        return await system.prune_images(node_id)

    # ── Bulk operations ─────────────────────────────────────────────────────

    async def bulk_container_action(
        self,
        node_ids: list[UUID],
        container_id: str,
        action: str,
        timeout: int | None = None,
    ) -> BulkDockerResultDTO:
        return await self._bulk.bulk_container_action(
            node_ids, container_id, action, timeout
        )

    async def bulk_exec(
        self, node_ids: list[UUID], container_id: str, command: str, timeout: int = 30
    ) -> BulkDockerResultDTO:
        return await self._bulk.bulk_exec(node_ids, container_id, command, timeout)

    async def bulk_inspect(
        self,
        node_ids: list[UUID],
        container_id: str,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        return await self._bulk.bulk_inspect(
            node_ids, container_id, node_tags=node_tags
        )

    async def bulk_logs(
        self,
        node_ids: list[UUID],
        container_id: str,
        tail: int = 100,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        return await self._bulk.bulk_logs(
            node_ids, container_id, tail=tail, node_tags=node_tags
        )

    async def bulk_stats(
        self,
        node_ids: list[UUID],
        container_id: str,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        return await self._bulk.bulk_stats(node_ids, container_id, node_tags=node_tags)


class _RepositoryNodeReader:
    """Temporary compatibility adapter for legacy facade callers."""

    def __init__(self, repository: NodeRepository) -> None:
        self._repository = repository

    @staticmethod
    def _to_connection(node: NodeModel | NodeConnectionDTO) -> NodeConnectionDTO:
        if isinstance(node, NodeConnectionDTO):
            return node
        return NodeConnectionDTO(
            id=node.id,
            name=node.name,
            endpoint=NodeEndpoint(
                host=node.host,
                port=node.port,
                connection_type=cast(ConnectionType, node.connection_type),
                docker_host=node.docker_host,
            ),
            credentials=NodeCredentials(
                username=node.username,
                password=node.password,
                ssh_key=node.ssh_key,
                passphrase=node.passphrase,
            ),
        )

    async def get_connection(self, node_id: UUID) -> NodeConnectionDTO | None:
        node = await self._repository.get_by_id(node_id)
        return self._to_connection(node) if node is not None else None

    async def get_connections_by_ids(
        self, node_ids: list[UUID]
    ) -> list[NodeConnectionDTO]:
        nodes = await self._repository.get_by_ids(node_ids)
        return [self._to_connection(node) for node in nodes]

    async def get_connections_by_tags(self, tags: list[str]) -> list[NodeConnectionDTO]:
        nodes = await self._repository.get_by_tags(tags)
        return [self._to_connection(node) for node in nodes]

    async def get_connections_by_type(
        self, connection_type: str
    ) -> list[NodeConnectionDTO]:
        nodes = await self._repository.get_connections_by_type(connection_type)
        return [self._to_connection(node) for node in nodes]
