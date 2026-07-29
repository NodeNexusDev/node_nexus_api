"""Compatibility facade for focused Docker application services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.docker_runtime import DockerRuntime
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory
    from app.repositories.node_repo import NodeRepository
    from app.services.audit_service import AuditService

from app.adapters.runtime.docker import SshDockerRuntime
from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.docker import (
    DockerContainerDTO,
    DockerContainerInspectDTO,
    DockerExecResultDTO,
    DockerImageDTO,
    DockerNetworkDTO,
    DockerPullResultDTO,
    DockerStatsDTO,
    DockerVolumeDTO,
)
from app.schemas.docker import (
    BulkDockerResponse,
)
from app.services.docker.bulk_service import DockerBulkService
from app.services.docker.command_runner import DockerCommandRunner
from app.services.docker.container_service import DockerContainerService
from app.services.docker.error_mapper import raise_for_docker_error
from app.services.docker.image_service import DockerImageService
from app.services.docker.parsers import parse_json_array, parse_json_lines
from app.services.docker.resource_service import DockerResourceService


class DockerService:
    """Stable facade delegating to focused Docker domain services."""

    def __init__(
        self,
        repository: NodeRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
        node_reader: NodeConnectionReader | None = None,
        runtime: DockerRuntime | None = None,
    ) -> None:
        self._audit = audit_service
        resolved_reader = node_reader or _RepositoryNodeReader(repository)
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
        details: dict[str, Any] | None = None,
    ) -> None:
        """Compatibility audit hook for internal callers."""
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    # Private compatibility methods retained for existing internal callers/tests.
    async def _get_docker_node(self, node_id: UUID) -> Any:
        return await self._runner.get_target(node_id)

    async def _execute_docker_cmd(
        self, node: Any, command: str, timeout: int = 30
    ) -> tuple[str, str, int]:
        return await self._runner.execute(node, command, timeout)

    def _build_docker_cmd(self, node: Any, docker_args: str) -> str:
        return self._runner.build_command(node, docker_args)

    @staticmethod
    def _parse_json_lines(stdout: str) -> list[dict[str, Any]]:
        return parse_json_lines(stdout)

    @staticmethod
    def _parse_json_array(stdout: str) -> list[dict[str, Any]]:
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

    async def bulk_container_action(
        self,
        node_ids: list[str],
        container_id: str,
        action: str,
        timeout: int | None = None,
    ) -> BulkDockerResponse:
        return await self._bulk.bulk_container_action(
            node_ids, container_id, action, timeout
        )

    async def bulk_exec(
        self, node_ids: list[str], container_id: str, command: str, timeout: int = 30
    ) -> BulkDockerResponse:
        return await self._bulk.bulk_exec(node_ids, container_id, command, timeout)


class _RepositoryNodeReader:
    """Temporary compatibility adapter for legacy facade callers."""

    def __init__(self, repository: NodeRepository) -> None:
        self._repository = repository

    async def get_connection(self, node_id: UUID) -> Any:
        return await self._repository.get_by_id(node_id)

    async def get_connections_by_ids(self, node_ids: list[UUID]) -> list[Any]:
        return await self._repository.get_connections_by_ids(node_ids)

    async def get_connections_by_tags(self, tags: list[str]) -> list[Any]:
        return await self._repository.get_connections_by_tags(tags)
