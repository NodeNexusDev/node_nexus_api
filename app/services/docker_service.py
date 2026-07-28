"""Docker service for business logic."""

from __future__ import annotations

import asyncio
import shlex
import uuid
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory
    from app.repositories.node_repo import NodeRepository
    from app.services.audit_service import AuditService

import structlog

from app.core.docker_validation import validate_container_id, validate_image_name
from app.core.exceptions import (
    ConnectionFailedError,
    ContainerNotFoundError,
    DockerError,
    NodeNotFoundError,
)
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.schemas.docker import (
    BulkDockerNodeResult,
    BulkDockerResponse,
    DockerContainer,
    DockerContainerConfig,
    DockerContainerInspect,
    DockerContainerState,
    DockerExecResult,
    DockerImage,
    DockerNetwork,
    DockerPullResult,
    DockerStats,
    DockerVolume,
)
from app.services.docker.command_builder import build_docker_command
from app.services.docker.error_mapper import raise_for_docker_error
from app.services.docker.parsers import parse_json_array, parse_json_lines

audit = structlog.get_logger("audit")


class DockerService:
    """Service for Docker operations via SSH."""

    def __init__(
        self,
        repository: NodeRepository,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
        node_reader: NodeConnectionReader | None = None,
    ):
        self._repository = repository
        self._audit = audit_service
        self._connector_factory = connector_factory
        self._node_reader = node_reader

    async def _log(
        self,
        action: str,
        node_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def _get_docker_node(self, node_id: UUID) -> Any:
        """Get node and validate connection_type='docker'."""
        node = (
            await self._node_reader.get_connection(node_id)
            if self._node_reader
            else await self._repository.get_by_id(node_id)
        )
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        if node.connection_type != "docker":
            raise DockerError(f"Node {node_id} is not a Docker node")
        return node

    async def _execute_docker_cmd(
        self, node: Any, command: str, timeout: int = 30
    ) -> tuple[str, str, int]:
        """Execute a docker CLI command via SSH."""
        password = decrypt_value(node.password)
        ssh_key = decrypt_value(node.ssh_key)
        connector = get_connector_factory(self._connector_factory).create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=password,
            ssh_key=ssh_key,
        )
        try:
            async with connector:
                return await connector.execute_command(command)
        except Exception as exc:
            raise ConnectionFailedError(
                f"Failed to connect to Docker host {node.host}: {exc}"
            ) from exc

    def _build_docker_cmd(self, node: Any, docker_args: str) -> str:
        """Build docker command with DOCKER_HOST if set."""
        return build_docker_command(node, docker_args)

    def _parse_json_lines(self, stdout: str) -> list[dict[str, Any]]:
        """Robust parsing of JSON lines from docker CLI output."""
        return parse_json_lines(stdout)

    def _parse_json_array(self, stdout: str) -> list[dict[str, Any]]:
        """Parse JSON array (docker inspect returns [{...}])."""
        return parse_json_array(stdout)

    def _map_docker_error(self, stderr: str, exit_code: int) -> None:
        """Map Docker CLI errors to domain exceptions."""
        raise_for_docker_error(stderr, exit_code)

    # --- Container operations ---

    async def list_containers(
        self, node_id: UUID, *, all: bool = False
    ) -> list[DockerContainer]:
        """List containers on a Docker node."""
        node = await self._get_docker_node(node_id)
        flag = " -a" if all else ""
        cmd = self._build_docker_cmd(node, f"ps{flag} --format '{{{{json .}}}}'")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        containers = self._parse_json_lines(stdout)
        audit.info(
            "docker.containers.list",
            node_id=str(node_id),
            count=len(containers),
        )
        await self._log(
            "docker.containers.list",
            node_id=node_id,
            details={"count": len(containers)},
        )
        return [DockerContainer.model_validate(c) for c in containers]

    async def get_container(
        self, node_id: UUID, container_id: str
    ) -> DockerContainerInspect:
        """Get container details."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, f"inspect {validated_id}")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        items = self._parse_json_array(stdout)
        if not items:
            raise ContainerNotFoundError(f"Container {validated_id} not found")
        data = items[0]
        state_data = data.get("State", {})
        config_data = data.get("Config", {})
        audit.info(
            "docker.container.inspect",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.inspect",
            node_id=node_id,
            details={"container_id": validated_id},
        )
        return DockerContainerInspect(
            id=data.get("Id", ""),
            name=data.get("Name", ""),
            state=DockerContainerState(
                status=state_data.get("Status", ""),
                running=state_data.get("Running", False),
                exit_code=state_data.get("ExitCode", 0),
                started_at=state_data.get("StartedAt"),
                finished_at=state_data.get("FinishedAt"),
                oom_killed=state_data.get("OOMKilled"),
            ),
            config=DockerContainerConfig(
                image=config_data.get("Image"),
                cmd=config_data.get("Cmd"),
                env=config_data.get("Env"),
                hostname=config_data.get("Hostname"),
            ),
            network_settings=data.get("NetworkSettings"),
        )

    async def start_container(self, node_id: UUID, container_id: str) -> None:
        """Start a container."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, f"start {validated_id}")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        audit.info(
            "docker.container.start",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.start",
            node_id=node_id,
            details={"container_id": validated_id},
        )

    async def stop_container(
        self, node_id: UUID, container_id: str, *, timeout: int = 10
    ) -> None:
        """Stop a container."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, f"stop -t {timeout} {validated_id}")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        audit.info(
            "docker.container.stop",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.stop",
            node_id=node_id,
            details={"container_id": validated_id, "timeout": timeout},
        )

    async def restart_container(
        self, node_id: UUID, container_id: str, *, timeout: int = 10
    ) -> None:
        """Restart a container."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, f"restart -t {timeout} {validated_id}")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        audit.info(
            "docker.container.restart",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.restart",
            node_id=node_id,
            details={"container_id": validated_id, "timeout": timeout},
        )

    async def remove_container(
        self, node_id: UUID, container_id: str, *, force: bool = False
    ) -> None:
        """Remove a container."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        force_flag = " -f" if force else ""
        cmd = self._build_docker_cmd(node, f"rm{force_flag} {validated_id}")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        audit.info(
            "docker.container.remove",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.remove",
            node_id=node_id,
            details={"container_id": validated_id, "force": force},
        )

    async def get_logs(
        self,
        node_id: UUID,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
    ) -> str:
        """Get container logs."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        since_flag = f" --since {since}" if since else ""
        cmd = self._build_docker_cmd(
            node, f"logs --tail {tail}{since_flag} {validated_id}"
        )
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        audit.info(
            "docker.container.logs",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.logs",
            node_id=node_id,
            details={"container_id": validated_id, "tail": tail},
        )
        return stdout

    async def exec_command(
        self,
        node_id: UUID,
        container_id: str,
        command: str,
        *,
        timeout: int = 30,
    ) -> DockerExecResult:
        """Execute a command in a container."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        escaped_cmd = shlex.quote(command)
        cmd = self._build_docker_cmd(node, f"exec {validated_id} sh -c {escaped_cmd}")
        stdout, stderr, exit_code = await self._execute_docker_cmd(
            node, cmd, timeout=timeout
        )
        if exit_code != 0:
            audit.warning(
                "docker.container.exec.failed",
                node_id=str(node_id),
                container_id=validated_id,
                exit_code=exit_code,
            )
        else:
            audit.info(
                "docker.container.exec.ok",
                node_id=str(node_id),
                container_id=validated_id,
            )
        await self._log(
            "docker.container.exec",
            node_id=node_id,
            details={
                "container_id": validated_id,
                "command": command,
                "exit_code": exit_code,
            },
        )
        return DockerExecResult(stdout=stdout, stderr=stderr, exit_code=exit_code)

    # --- Image operations ---

    async def list_images(self, node_id: UUID) -> list[DockerImage]:
        """List images on a Docker node."""
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, "images --format '{{json .}}'")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        images = self._parse_json_lines(stdout)
        audit.info(
            "docker.images.list",
            node_id=str(node_id),
            count=len(images),
        )
        await self._log(
            "docker.images.list",
            node_id=node_id,
            details={"count": len(images)},
        )
        return [DockerImage.model_validate(img) for img in images]

    async def pull_image(
        self, node_id: UUID, image: str, *, timeout: int = 300
    ) -> DockerPullResult:
        """Pull a Docker image."""
        validated_image = validate_image_name(image)
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, f"pull {validated_image}")
        try:
            stdout, stderr, exit_code = await self._execute_docker_cmd(
                node, cmd, timeout=timeout
            )
        except ConnectionFailedError as exc:
            audit.error(
                "docker.image.pull.failed",
                node_id=str(node_id),
                image=validated_image,
                error=str(exc),
            )
            await self._log(
                "docker.image.pull",
                node_id=node_id,
                details={"image": validated_image, "success": False},
            )
            return DockerPullResult(
                image=validated_image, output=str(exc), success=False
            )

        self._map_docker_error(stderr, exit_code)
        success = exit_code == 0
        output = stdout if success else stderr
        audit.info(
            "docker.image.pull.ok" if success else "docker.image.pull.failed",
            node_id=str(node_id),
            image=validated_image,
        )
        await self._log(
            "docker.image.pull",
            node_id=node_id,
            details={"image": validated_image, "success": success},
        )
        return DockerPullResult(image=validated_image, output=output, success=success)

    # --- Stats ---

    async def get_stats(self, node_id: UUID, container_id: str) -> DockerStats:
        """Get container stats."""
        validated_id = validate_container_id(container_id)
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(
            node, f"stats --no-stream --format '{{{{json .}}}}' {validated_id}"
        )
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        items = self._parse_json_lines(stdout)
        if not items:
            raise ContainerNotFoundError(
                f"Container {validated_id} not found or not running"
            )
        audit.info(
            "docker.container.stats",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.stats",
            node_id=node_id,
            details={"container_id": validated_id},
        )
        return DockerStats.model_validate(items[0])

    # --- Network and Volume operations ---

    async def list_networks(self, node_id: UUID) -> list[DockerNetwork]:
        """List Docker networks."""
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, "network ls --format '{{json .}}'")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        networks = self._parse_json_lines(stdout)
        audit.info(
            "docker.networks.list",
            node_id=str(node_id),
            count=len(networks),
        )
        await self._log(
            "docker.networks.list",
            node_id=node_id,
            details={"count": len(networks)},
        )
        return [DockerNetwork.model_validate(n) for n in networks]

    async def list_volumes(self, node_id: UUID) -> list[DockerVolume]:
        """List Docker volumes."""
        node = await self._get_docker_node(node_id)
        cmd = self._build_docker_cmd(node, "volume ls --format '{{json .}}'")
        stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
        self._map_docker_error(stderr, exit_code)
        volumes = self._parse_json_lines(stdout)
        audit.info(
            "docker.volumes.list",
            node_id=str(node_id),
            count=len(volumes),
        )
        await self._log(
            "docker.volumes.list",
            node_id=node_id,
            details={"count": len(volumes)},
        )
        return [DockerVolume.model_validate(v) for v in volumes]

    # --- Bulk operations ---

    async def bulk_container_action(
        self,
        node_ids: list[str],
        container_id: str,
        action: str,
        timeout: int | None = None,
    ) -> BulkDockerResponse:
        """Perform a Docker action on multiple nodes in parallel.

        Args:
            node_ids: List of node ID strings.
            container_id: Container ID or name.
            action: Docker action (start, stop, restart).
            timeout: Optional timeout for stop/restart actions.

        Returns:
            BulkDockerResponse with per-node results.
        """
        validated_id = validate_container_id(container_id)

        prepared: list[tuple[int, str, Any]] = []
        results: list[BulkDockerNodeResult | None] = [None] * len(node_ids)
        for index, node_id_str in enumerate(node_ids):
            try:
                node_id = uuid.UUID(node_id_str)
                node = await self._get_docker_node(node_id)
                prepared.append((index, node_id_str, node))
            except NodeNotFoundError:
                results[index] = BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error="Node not found",
                )
            except (ValueError, DockerError) as exc:
                results[index] = BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        async def _action_on_node(node_id_str: str, node: Any) -> BulkDockerNodeResult:
            try:
                if action == "start":
                    cmd = self._build_docker_cmd(node, f"start {validated_id}")
                elif action == "stop":
                    t = timeout or 10
                    cmd = self._build_docker_cmd(node, f"stop -t {t} {validated_id}")
                elif action == "restart":
                    t = timeout or 10
                    cmd = self._build_docker_cmd(node, f"restart -t {t} {validated_id}")
                else:
                    raise DockerError(f"Unknown action: {action}")
                stdout, stderr, exit_code = await self._execute_docker_cmd(node, cmd)
                if exit_code != 0 and stderr:
                    return BulkDockerNodeResult(
                        node_id=node_id_str,
                        node_name=node.name,
                        status="error",
                        error=stderr.strip(),
                    )
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success",
                    output=stdout.strip(),
                )
            except DockerError as exc:
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )
            except Exception as exc:
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote_results = await asyncio.gather(
            *(_action_on_node(node_id_str, node) for _, node_id_str, node in prepared)
        )
        for (index, _, _), result in zip(prepared, remote_results, strict=True):
            results[index] = result
        final_results = [result for result in results if result is not None]

        succeeded = sum(1 for r in final_results if r.status == "success")
        failed = len(final_results) - succeeded

        audit.info(
            "docker.bulk.action",
            action=action,
            container_id=validated_id,
            total=len(final_results),
            succeeded=succeeded,
            failed=failed,
        )

        return BulkDockerResponse(
            action=action,
            results=final_results,
            total=len(final_results),
            succeeded=succeeded,
            failed=failed,
        )

    async def bulk_exec(
        self, node_ids: list[str], container_id: str, command: str, timeout: int = 30
    ) -> BulkDockerResponse:
        """Execute a command in a container on multiple nodes.

        Args:
            node_ids: List of node ID strings.
            container_id: Container ID or name.
            command: Command to execute.
            timeout: Timeout in seconds.

        Returns:
            BulkDockerResponse with per-node results.
        """
        validated_id = validate_container_id(container_id)

        prepared: list[tuple[int, str, Any]] = []
        results: list[BulkDockerNodeResult | None] = [None] * len(node_ids)
        for index, node_id_str in enumerate(node_ids):
            try:
                node_id = uuid.UUID(node_id_str)
                node = await self._get_docker_node(node_id)
                prepared.append((index, node_id_str, node))
            except NodeNotFoundError:
                results[index] = BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error="Node not found",
                )
            except (ValueError, DockerError) as exc:
                results[index] = BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        async def _exec_on_node(node_id_str: str, node: Any) -> BulkDockerNodeResult:
            try:
                escaped_cmd = shlex.quote(command)
                docker_cmd = self._build_docker_cmd(
                    node, f"exec {validated_id} sh -c {escaped_cmd}"
                )
                stdout, stderr, exit_code = await self._execute_docker_cmd(
                    node, docker_cmd, timeout=timeout
                )

                if exit_code != 0:
                    return BulkDockerNodeResult(
                        node_id=node_id_str,
                        node_name=node.name,
                        status="error",
                        output=stdout.strip(),
                        error=stderr.strip(),
                    )
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success",
                    output=stdout.strip(),
                )
            except DockerError as exc:
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )
            except Exception as exc:
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote_results = await asyncio.gather(
            *(_exec_on_node(node_id_str, node) for _, node_id_str, node in prepared)
        )
        for (index, _, _), result in zip(prepared, remote_results, strict=True):
            results[index] = result
        final_results = [result for result in results if result is not None]

        succeeded = sum(1 for r in final_results if r.status == "success")
        failed = len(final_results) - succeeded

        audit.info(
            "docker.bulk.exec",
            container_id=validated_id,
            total=len(final_results),
            succeeded=succeeded,
            failed=failed,
        )

        return BulkDockerResponse(
            action="exec",
            results=final_results,
            total=len(final_results),
            succeeded=succeeded,
            failed=failed,
        )
