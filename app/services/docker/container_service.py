"""Docker container use cases."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.services.audit_service import AuditService

import structlog

from app.application.dto.docker import (
    DockerContainerConfigDTO,
    DockerContainerDTO,
    DockerContainerInspectDTO,
    DockerContainerStateDTO,
    DockerExecResultDTO,
    DockerStatsDTO,
)
from app.core.connectors.ssh import command_fingerprint
from app.core.docker_validation import validate_container_id
from app.core.exceptions import ContainerNotFoundError
from app.services.docker.command_runner import DockerCommandRunner
from app.services.docker.error_mapper import raise_for_docker_error
from app.services.docker.parsers import parse_json_array, parse_json_lines

audit = structlog.get_logger("audit")


class DockerContainerService:
    """Container operations composed over the shared command runner."""

    def __init__(
        self, runner: DockerCommandRunner, audit_service: AuditService | None = None
    ) -> None:
        self._runner = runner
        self._audit = audit_service

    async def _log(self, action: str, node_id: UUID, details: dict[str, Any]) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def _log_required(
        self, action: str, node_id: UUID, details: dict[str, Any]
    ) -> None:
        if self._audit:
            await self._audit.log_required(
                action=action, node_id=node_id, details=details
            )

    async def list_containers(
        self, node_id: UUID, *, all: bool = False
    ) -> list[DockerContainerDTO]:
        node = await self._runner.get_target(node_id)
        flag = " -a" if all else ""
        cmd = self._runner.build_command(node, f"ps{flag} --format '{{{{json .}}}}'")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_lines(stdout)
        audit.info("docker.containers.list", node_id=str(node_id), count=len(items))
        await self._log("docker.containers.list", node_id, {"count": len(items)})
        return [
            DockerContainerDTO(
                id=item["ID"],
                names=item["Names"],
                image=item["Image"],
                command=item["Command"],
                created_at=item["CreatedAt"],
                state=item["State"],
                status=item["Status"],
                ports=item.get("Ports"),
                networks=item.get("Networks"),
            )
            for item in items
        ]

    async def get_container(
        self, node_id: UUID, container_id: str
    ) -> DockerContainerInspectDTO:
        validated_id = validate_container_id(container_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, f"inspect {validated_id}")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_array(stdout)
        if not items:
            raise ContainerNotFoundError(f"Container {validated_id} not found")
        data = items[0]
        state = data.get("State", {})
        config = data.get("Config", {})
        audit.info(
            "docker.container.inspect",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.inspect", node_id, {"container_id": validated_id}
        )
        return DockerContainerInspectDTO(
            id=data.get("Id", ""),
            name=data.get("Name", ""),
            state=DockerContainerStateDTO(
                status=state.get("Status", ""),
                running=state.get("Running", False),
                exit_code=state.get("ExitCode", 0),
                started_at=state.get("StartedAt"),
                finished_at=state.get("FinishedAt"),
                oom_killed=state.get("OOMKilled"),
            ),
            config=DockerContainerConfigDTO(
                image=config.get("Image"),
                cmd=tuple(config["Cmd"]) if config.get("Cmd") else None,
                hostname=config.get("Hostname"),
            ),
            network_settings=tuple((data.get("NetworkSettings") or {}).items()),
        )

    async def _lifecycle_action(
        self,
        node_id: UUID,
        container_id: str,
        action: str,
        args: str,
        details: dict[str, Any],
    ) -> None:
        validated_id = validate_container_id(container_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, f"{args} {validated_id}")
        await self._log_required(
            f"docker.container.{action}.requested",
            node_id,
            {"container_id": validated_id},
        )
        _, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        event = f"docker.container.{action}"
        audit.info(event, node_id=str(node_id), container_id=validated_id)
        await self._log(event, node_id, {"container_id": validated_id, **details})

    async def start_container(self, node_id: UUID, container_id: str) -> None:
        await self._lifecycle_action(node_id, container_id, "start", "start", {})

    async def stop_container(
        self, node_id: UUID, container_id: str, *, timeout: int = 10
    ) -> None:
        await self._lifecycle_action(
            node_id, container_id, "stop", f"stop -t {timeout}", {"timeout": timeout}
        )

    async def restart_container(
        self, node_id: UUID, container_id: str, *, timeout: int = 10
    ) -> None:
        await self._lifecycle_action(
            node_id,
            container_id,
            "restart",
            f"restart -t {timeout}",
            {"timeout": timeout},
        )

    async def remove_container(
        self, node_id: UUID, container_id: str, *, force: bool = False
    ) -> None:
        args = "rm -f" if force else "rm"
        await self._lifecycle_action(
            node_id, container_id, "remove", args, {"force": force}
        )

    async def get_logs(
        self,
        node_id: UUID,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
    ) -> str:
        validated_id = validate_container_id(container_id)
        node = await self._runner.get_target(node_id)
        since_flag = f" --since {since}" if since else ""
        cmd = self._runner.build_command(
            node, f"logs --tail {tail}{since_flag} {validated_id}"
        )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info(
            "docker.container.logs",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.logs",
            node_id,
            {"container_id": validated_id, "tail": tail},
        )
        return stdout

    async def exec_command(
        self,
        node_id: UUID,
        container_id: str,
        command: str,
        *,
        timeout: int = 30,
    ) -> DockerExecResultDTO:
        validated_id = validate_container_id(container_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(
            node, f"exec {validated_id} sh -c {shlex.quote(command)}"
        )
        await self._log_required(
            "docker.container.exec.requested",
            node_id,
            {
                "container_id": validated_id,
                "command_fingerprint": command_fingerprint(command),
            },
        )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd, timeout)
        event = (
            "docker.container.exec.ok"
            if exit_code == 0
            else "docker.container.exec.failed"
        )
        (audit.info if exit_code == 0 else audit.warning)(
            event,
            node_id=str(node_id),
            container_id=validated_id,
            exit_code=exit_code,
        )
        await self._log(
            "docker.container.exec",
            node_id,
            {
                "container_id": validated_id,
                "command": command,
                "exit_code": exit_code,
            },
        )
        return DockerExecResultDTO(stdout=stdout, stderr=stderr, exit_code=exit_code)

    async def get_stats(self, node_id: UUID, container_id: str) -> DockerStatsDTO:
        validated_id = validate_container_id(container_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(
            node, f"stats --no-stream --format '{{{{json .}}}}' {validated_id}"
        )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_lines(stdout)
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
            "docker.container.stats", node_id, {"container_id": validated_id}
        )
        item = items[0]
        return DockerStatsDTO(
            container_id=item["Container"],
            name=item["Name"],
            cpu_percent=item["CPUPerc"],
            mem_usage=item["MemUsage"],
            mem_limit=item.get("MemLimit"),
            mem_percent=item["MemPerc"],
            net_io=item["NetIO"],
            block_io=item["BlockIO"],
            pids=item.get("PIDs"),
        )
