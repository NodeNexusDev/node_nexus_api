"""Docker system-level use cases: info, df, prune."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink

import structlog

from app.application.dto.docker import (
    DockerPruneResultDTO,
    DockerSystemDfDTO,
    DockerSystemInfoDTO,
)
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.application.services.docker.parsers import json_string, parse_json_array

audit = structlog.get_logger("audit")


class DockerSystemService:
    """System-level Docker operations."""

    def __init__(
        self,
        runner: DockerCommandRunner,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._runner = runner
        self._audit = audit_service

    async def info(self, node_id: UUID) -> DockerSystemInfoDTO:
        """Return ``docker info`` parsed into a DTO."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "info --format '{{json .}}'")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_array(stdout)
        if not items:
            raise_for_docker_error("docker info returned empty output", 1)
        info = items[0]
        audit.info("docker.system.info", node_id=str(node_id))
        return DockerSystemInfoDTO(
            server_version=json_string(info, "ServerVersion"),
            storage_driver=json_string(info, "Driver"),
            operating_system=json_string(info, "OperatingSystem"),
            architecture=json_string(info, "Architecture"),
            total_memory=json_string(info, "MemTotal"),
            cpus=info.get("NCPU", 0) if isinstance(info.get("NCPU"), int) else 0,
            containers_running=info.get("ContainersRunning", 0)
            if isinstance(info.get("ContainersRunning"), int)
            else 0,
            containers_stopped=info.get("ContainersStopped", 0)
            if isinstance(info.get("ContainersStopped"), int)
            else 0,
            images=info.get("Images", 0) if isinstance(info.get("Images"), int) else 0,
        )

    async def disk_usage(self, node_id: UUID) -> list[DockerSystemDfDTO]:
        """Return ``docker system df`` parsed into DTOs."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "system df --format '{{json .}}'")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        lines = [line for line in stdout.strip().splitlines() if line.strip()]
        import json as _json

        results: list[DockerSystemDfDTO] = []
        for line in lines:
            try:
                item = _json.loads(line)
                results.append(
                    DockerSystemDfDTO(
                        type=json_string(item, "Type"),
                        total_count=item.get("TotalCount", 0)
                        if isinstance(item.get("TotalCount"), int)
                        else 0,
                        active_size=json_string(item, "ActiveSize"),
                        reclaimable_size=json_string(item, "Reclaimable"),
                        reclaimable_percent=json_string(item, "ReclaimablePercent"),
                    )
                )
            except (_json.JSONDecodeError, KeyError):
                continue
        audit.info("docker.system.df", node_id=str(node_id), count=len(results))
        return results

    async def prune_containers(self, node_id: UUID) -> DockerPruneResultDTO:
        """Prune stopped containers."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "container prune -f")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        output = stdout.strip()
        deleted: tuple[str, ...] = ()
        space = ""
        for line in output.splitlines():
            if line.startswith("Deleted"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    ids = [x.strip() for x in parts[1].split(",") if x.strip()]
                    deleted = tuple(ids)
            if "reclaimed" in line.lower():
                space = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
        audit.info("docker.containers.prune", node_id=str(node_id))
        if self._audit:
            await self._audit.log(
                action="docker.containers.prune",
                node_id=node_id,
                details={"deleted": len(deleted), "space_reclaimed": space},
            )
        return DockerPruneResultDTO(
            containers_deleted=deleted,
            space_reclaimed=space,
        )

    async def prune_images(self, node_id: UUID) -> DockerPruneResultDTO:
        """Prune unused images."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "image prune -f")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        output = stdout.strip()
        deleted: tuple[str, ...] = ()
        space = ""
        for line in output.splitlines():
            if line.startswith("Deleted"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    ids = [x.strip() for x in parts[1].split(",") if x.strip()]
                    deleted = tuple(ids)
            if "reclaimed" in line.lower():
                space = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
        audit.info("docker.images.prune", node_id=str(node_id))
        if self._audit:
            await self._audit.log(
                action="docker.images.prune",
                node_id=node_id,
                details={"deleted": len(deleted), "space_reclaimed": space},
            )
        return DockerPruneResultDTO(
            images_deleted=deleted,
            space_reclaimed=space,
        )
