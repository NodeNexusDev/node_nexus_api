"""Docker container use cases."""

from __future__ import annotations

import shlex
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink

import structlog

from app.application.command_policy import command_fingerprint
from app.application.dto.docker import (
    ContainerCreatedDTO,
    ContainerCreateRequestDTO,
    DockerContainerConfigDTO,
    DockerContainerDTO,
    DockerContainerInspectDTO,
    DockerContainerStateDTO,
    DockerExecResultDTO,
    DockerStatsDTO,
)
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.application.services.docker.parsers import (
    json_optional_string,
    json_string,
    parse_json_array,
    parse_json_lines,
)
from app.application.types import JsonObject
from app.core.docker_validation import (
    validate_container_id,
    validate_container_name,
    validate_env_vars,
    validate_image_name,
    validate_labels,
    validate_network_name,
    validate_port_mappings,
    validate_restart_policy,
    validate_volume_mounts,
)
from app.core.exceptions import ContainerNotFoundError, DockerValidationError

audit = structlog.get_logger("audit")


def parse_since(since: str) -> str:
    """Accept a Unix timestamp or ISO 8601 string and return a Docker-safe value.

    Docker's ``--since`` flag accepts both formats, but we normalize ISO 8601
    inputs to seconds-since-epoch to keep the behavior consistent across
    Docker versions and to reject ambiguous strings early.
    """
    if since.isdigit():
        return since  # Unix timestamp — pass through unchanged.
    normalized = since.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DockerValidationError(
            f"Invalid 'since' value: {since!r}. "
            "Expected a Unix timestamp or an ISO 8601 string."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.astimezone()  # assume local time when no offset is provided
    return str(int(dt.timestamp()))


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _boolean(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(item for item in value if isinstance(item, str))


class DockerContainerService:
    """Container operations composed over the shared command runner."""

    def __init__(
        self,
        runner: DockerCommandRunner,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._runner = runner
        self._audit = audit_service

    async def _log(self, action: str, node_id: UUID, details: JsonObject) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def _log_required(
        self, action: str, node_id: UUID, details: JsonObject
    ) -> None:
        if self._audit:
            await self._audit.log_required(
                action=action, node_id=node_id, details=details
            )

    @staticmethod
    def _build_create_args(request: ContainerCreateRequestDTO) -> str:
        """Assemble a fully-shell-quoted ``docker create`` argument string."""
        parts: list[str] = []
        if request.name is not None:
            parts.append(f"--name {shlex.quote(request.name)}")
        if request.restart_policy is not None:
            parts.append(f"--restart {shlex.quote(request.restart_policy)}")
        for container_spec, host_port in request.ports:
            parts.append(f"-p {shlex.quote(host_port)}:{shlex.quote(container_spec)}")
        for host_path, bind, mode in request.volumes:
            parts.append(
                f"-v {shlex.quote(host_path)}:{shlex.quote(bind)}:{shlex.quote(mode)}"
            )
        for entry in request.env:
            parts.append(f"-e {shlex.quote(entry)}")
        for key, value in request.labels:
            parts.append(f"--label {shlex.quote(f'{key}={value}')}")
        if request.network is not None:
            parts.append(f"--network {shlex.quote(request.network)}")
        parts.append(shlex.quote(request.image))
        if request.command:
            parts.append(shlex.quote(request.command))
        return "create " + " ".join(parts)

    async def create_container(
        self, request: ContainerCreateRequestDTO
    ) -> ContainerCreatedDTO:
        """Create a container via ``docker create`` and return its ID."""
        validated_image = validate_image_name(request.image)
        name: str | None = None
        if request.name is not None:
            name = validate_container_name(request.name)
        ports = validate_port_mappings(dict(request.ports))
        volumes = validate_volume_mounts(
            {hp: {"bind": b, "mode": m} for hp, b, m in request.volumes}
        )
        env = validate_env_vars(list(request.env))
        labels = validate_labels(dict(request.labels))
        network = validate_network_name(request.network) if request.network else None
        restart_policy = (
            validate_restart_policy(request.restart_policy)
            if request.restart_policy
            else None
        )
        normalized = ContainerCreateRequestDTO(
            node_id=request.node_id,
            image=validated_image,
            name=name,
            command=request.command,
            ports=tuple(ports.items()),
            volumes=tuple((hp, v["bind"], v["mode"]) for hp, v in volumes.items()),
            env=tuple(env),
            labels=tuple(labels.items()),
            network=network,
            restart_policy=restart_policy,
        )
        node = await self._runner.get_target(request.node_id)
        args = self._build_create_args(normalized)
        cmd = self._runner.build_command(node, args)
        await self._log_required(
            "docker.container.create.requested",
            request.node_id,
            {"image": validated_image, "name": name or ""},
        )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd, timeout=120)
        raise_for_docker_error(stderr, exit_code)
        container_id = stdout.strip().splitlines()[-1].strip() if stdout.strip() else ""
        if not container_id:
            raise DockerValidationError(
                f"docker create produced no container id: {stderr.strip()}"
            )
        audit.info(
            "docker.container.create",
            node_id=str(request.node_id),
            image=validated_image,
            container_id=container_id,
        )
        await self._log(
            "docker.container.create",
            request.node_id,
            {"container_id": container_id, "image": validated_image},
        )
        return ContainerCreatedDTO(
            id=container_id,
            name=name or container_id,
            image=validated_image,
            status="created",
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
                id=json_string(item, "ID"),
                names=json_string(item, "Names"),
                image=json_string(item, "Image"),
                command=json_string(item, "Command"),
                created_at=json_string(item, "CreatedAt"),
                state=json_string(item, "State"),
                status=json_string(item, "Status"),
                ports=json_optional_string(item, "Ports"),
                networks=json_optional_string(item, "Networks"),
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
        state = _json_object(data.get("State"))
        config = _json_object(data.get("Config"))
        network_settings = _json_object(data.get("NetworkSettings"))
        audit.info(
            "docker.container.inspect",
            node_id=str(node_id),
            container_id=validated_id,
        )
        await self._log(
            "docker.container.inspect", node_id, {"container_id": validated_id}
        )
        return DockerContainerInspectDTO(
            id=_string(data.get("Id")),
            name=_string(data.get("Name")),
            state=DockerContainerStateDTO(
                status=_string(state.get("Status")),
                running=_boolean(state.get("Running")),
                exit_code=_integer(state.get("ExitCode")),
                started_at=_optional_string(state.get("StartedAt")),
                finished_at=_optional_string(state.get("FinishedAt")),
                oom_killed=(
                    _boolean(state["OOMKilled"]) if "OOMKilled" in state else None
                ),
            ),
            config=DockerContainerConfigDTO(
                image=_optional_string(config.get("Image")),
                cmd=_string_tuple(config.get("Cmd")),
                hostname=_optional_string(config.get("Hostname")),
            ),
            network_settings=tuple(network_settings.items()),
        )

    async def _lifecycle_action(
        self,
        node_id: UUID,
        container_id: str,
        action: str,
        args: str,
        details: JsonObject,
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
        normalized_since = parse_since(since) if since else None
        node = await self._runner.get_target(node_id)
        since_flag = f" --since {normalized_since}" if normalized_since else ""
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
            container_id=json_string(item, "Container"),
            name=json_string(item, "Name"),
            cpu_percent=json_string(item, "CPUPerc"),
            mem_usage=json_string(item, "MemUsage"),
            mem_limit=json_optional_string(item, "MemLimit"),
            mem_percent=json_string(item, "MemPerc"),
            net_io=json_string(item, "NetIO"),
            block_io=json_string(item, "BlockIO"),
            pids=json_optional_string(item, "PIDs"),
        )
