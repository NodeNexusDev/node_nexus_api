"""Docker system-level use cases: info, df, prune."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink

import structlog

from app.application.dto.docker import (
    DockerPruneResultDTO,
    DockerSystemDfDTO,
    DockerSystemInfoDTO,
    DockerSystemVersionDTO,
)
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.application.services.docker.parsers import (
    json_string,
    parse_json_array,
    parse_json_lines,
)

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
            cpus=cast(int, info.get("NCPU"))
            if isinstance(info.get("NCPU"), int)
            else 0,
            containers_running=cast(int, info.get("ContainersRunning"))
            if isinstance(info.get("ContainersRunning"), int)
            else 0,
            containers_stopped=cast(int, info.get("ContainersStopped"))
            if isinstance(info.get("ContainersStopped"), int)
            else 0,
            images=cast(int, info.get("Images"))
            if isinstance(info.get("Images"), int)
            else 0,
        )

    async def disk_usage(self, node_id: UUID) -> list[DockerSystemDfDTO]:
        """Return ``docker system df`` parsed into DTOs."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "system df --format '{{json .}}'")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        lines = [line for line in stdout.strip().splitlines() if line.strip()]
        import json as _json_local

        results: list[DockerSystemDfDTO] = []
        for line in lines:
            try:
                item = _json_local.loads(line)
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
            except (_json_local.JSONDecodeError, KeyError):
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

    async def version(self, node_id: UUID) -> DockerSystemVersionDTO:
        """Return ``docker version`` parsed into a DTO."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "version --format '{{json .}}'")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_array(stdout)
        if not items:
            # fallback try lines
            items = parse_json_lines(stdout)
        if not items:
            raise_for_docker_error("docker version returned empty output", 1)
        info = items[0]
        # docker version JSON may be nested under Server/Client
        server = (
            info.get("Server", info) if isinstance(info.get("Server"), dict) else info
        )
        if not isinstance(server, dict):
            server = info
        audit.info("docker.system.version", node_id=str(node_id))
        return DockerSystemVersionDTO(
            server_version=json_string(server, "Version")
            or json_string(info, "ServerVersion")
            or json_string(info, "Version"),
            api_version=json_string(server, "ApiVersion")
            or json_string(info, "APIVersion"),
            go_version=json_string(server, "GoVersion")
            or json_string(info, "GoVersion"),
            git_commit=json_string(server, "GitCommit"),
            build_time=json_string(server, "BuildTime"),
            os=json_string(server, "Os"),
            arch=json_string(server, "Arch"),
        )

    async def system_prune(
        self, node_id: UUID, *, volumes: bool = False
    ) -> DockerPruneResultDTO:
        """Prune system via ``docker system prune``."""
        node = await self._runner.get_target(node_id)
        flag = " --volumes" if volumes else ""
        cmd = self._runner.build_command(node, f"system prune -f{flag}")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        output = stdout.strip()
        deleted: tuple[str, ...] = ()
        space = ""
        for line in output.splitlines():
            if "reclaimed" in line.lower():
                space = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
            if line.strip().startswith("Deleted"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    ids = [x.strip() for x in parts[1].split(",") if x.strip()]
                    deleted = tuple(ids)
        audit.info("docker.system.prune", node_id=str(node_id), volumes=volumes)
        if self._audit:
            await self._audit.log(
                action="docker.system.prune",
                node_id=node_id,
                details={"volumes": volumes, "space_reclaimed": space},
            )
        return DockerPruneResultDTO(
            containers_deleted=deleted,
            images_deleted=deleted,
            space_reclaimed=space,
        )
