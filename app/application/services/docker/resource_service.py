"""Docker network and volume use cases."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, cast
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink

import structlog

from app.application.dto.docker import (
    DockerNetworkDTO,
    DockerNetworkInspectDTO,
    DockerVolumeDTO,
    DockerVolumeInspectDTO,
    NetworkConnectRequestDTO,
    NetworkCreateRequestDTO,
    NetworkDisconnectRequestDTO,
    VolumeCreateRequestDTO,
)
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.application.services.docker.parsers import (
    json_string,
    parse_json_array,
    parse_json_lines,
)
from app.core.docker_validation import (
    validate_container_id,
    validate_ip_address,
    validate_network_driver,
    validate_volume_name,
)

audit = structlog.get_logger("audit")


class DockerResourceService:
    """Network and volume listing operations."""

    def __init__(
        self,
        runner: DockerCommandRunner,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._runner = runner
        self._audit = audit_service

    async def _list_raw(
        self,
        node_id: UUID,
        docker_args: str,
        event: str,
    ) -> list[dict[str, object]]:
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, docker_args)
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_lines(stdout)
        audit.info(event, node_id=str(node_id), count=len(items))
        if self._audit:
            await self._audit.log(
                action=event, node_id=node_id, details={"count": len(items)}
            )
        return items

    async def list_networks(self, node_id: UUID) -> list[DockerNetworkDTO]:
        items = await self._list_raw(
            node_id,
            "network ls --format '{{json .}}'",
            "docker.networks.list",
        )
        return [
            DockerNetworkDTO(
                id=json_string(item, "ID"),
                name=json_string(item, "Name"),
                driver=json_string(item, "Driver"),
                scope=json_string(item, "Scope"),
            )
            for item in items
        ]

    async def list_volumes(self, node_id: UUID) -> list[DockerVolumeDTO]:
        items = await self._list_raw(
            node_id,
            "volume ls --format '{{json .}}'",
            "docker.volumes.list",
        )
        return [
            DockerVolumeDTO(
                driver=json_string(item, "Driver"),
                name=json_string(item, "Name"),
            )
            for item in items
        ]

    # ── Network CRUD ────────────────────────────────────────────────────────

    async def create_network(self, data: NetworkCreateRequestDTO) -> str:
        """Create a Docker network and return the network ID."""
        validate_network_driver(data.driver)
        parts = ["network create", "--driver", shlex.quote(data.driver)]
        if data.subnet:
            parts.append(f"--subnet {shlex.quote(data.subnet)}")
        if data.gateway:
            parts.append(f"--gateway {shlex.quote(data.gateway)}")
        parts.append(shlex.quote(data.name))
        node = await self._runner.get_target(data.node_id)
        cmd = self._runner.build_command(node, " ".join(parts))
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        network_id = stdout.strip()
        audit.info(
            "docker.networks.create",
            node_id=str(data.node_id),
            name=data.name,
            network_id=network_id,
        )
        if self._audit:
            await self._audit.log(
                action="docker.networks.create",
                node_id=data.node_id,
                details={"name": data.name, "network_id": network_id},
            )
        return network_id

    async def inspect_network(
        self, node_id: UUID, network_id: str
    ) -> DockerNetworkInspectDTO:
        """Inspect a Docker network."""
        validate_container_id(network_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(
            node, f"network inspect {shlex.quote(network_id)}"
        )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_array(stdout)
        if not items:
            raise_for_docker_error(f"Network {network_id!r} not found", 1)
        net = items[0]
        containers_raw = cast(dict[str, dict[str, object]], net.get("Containers") or {})
        containers: list[tuple[str, dict[str, object]]] = []
        for cid, cdata in containers_raw.items():
            if isinstance(cdata, dict):
                containers.append(
                    (
                        cid,
                        {
                            "Name": json_string(cdata, "Name"),
                            "IPv4Address": json_string(cdata, "IPv4Address"),
                            "IPv6Address": json_string(cdata, "IPv6Address"),
                        },
                    )
                )
        ipam = net.get("IPAM", {})
        config = ipam.get("Config", [{}]) if isinstance(ipam, dict) else [{}]
        subnet = json_string(config[0], "Subnet") if config else ""
        gateway = json_string(config[0], "Gateway") if config else ""
        audit.info(
            "docker.networks.inspect",
            node_id=str(node_id),
            network_id=network_id,
        )
        return DockerNetworkInspectDTO(
            id=json_string(net, "Id"),
            name=json_string(net, "Name"),
            driver=json_string(net, "Driver"),
            scope=json_string(net, "Scope"),
            subnet=subnet,
            gateway=gateway,
            containers=tuple(containers),
        )

    async def remove_network(self, node_id: UUID, network_id: str) -> None:
        """Remove a Docker network."""
        validate_container_id(network_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, f"network rm {shlex.quote(network_id)}")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info(
            "docker.networks.remove",
            node_id=str(node_id),
            network_id=network_id,
        )
        if self._audit:
            await self._audit.log(
                action="docker.networks.remove",
                node_id=node_id,
                details={"network_id": network_id},
            )

    async def connect_to_network(self, data: NetworkConnectRequestDTO) -> None:
        """Connect a container to a network."""
        validate_container_id(data.network_id)
        validate_container_id(data.container_id)
        parts = ["network connect"]
        if data.ip_address:
            validate_ip_address(data.ip_address)
            parts.append(f"--ip {shlex.quote(data.ip_address)}")
        parts.append(shlex.quote(data.network_id))
        parts.append(shlex.quote(data.container_id))
        node = await self._runner.get_target(data.node_id)
        cmd = self._runner.build_command(node, " ".join(parts))
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info(
            "docker.networks.connect",
            node_id=str(data.node_id),
            network_id=data.network_id,
            container_id=data.container_id,
        )

    async def disconnect_from_network(self, data: NetworkDisconnectRequestDTO) -> None:
        """Disconnect a container from a network."""
        validate_container_id(data.network_id)
        validate_container_id(data.container_id)
        parts = ["network disconnect"]
        if data.force:
            parts.append("--force")
        parts.append(shlex.quote(data.network_id))
        parts.append(shlex.quote(data.container_id))
        node = await self._runner.get_target(data.node_id)
        cmd = self._runner.build_command(node, " ".join(parts))
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info(
            "docker.networks.disconnect",
            node_id=str(data.node_id),
            network_id=data.network_id,
            container_id=data.container_id,
        )

    # ── Volume CRUD ─────────────────────────────────────────────────────────

    async def create_volume(self, data: VolumeCreateRequestDTO) -> str:
        """Create a Docker volume and return the volume name."""
        parts = ["volume create"]
        if data.name:
            validate_volume_name(data.name)
            parts.append(shlex.quote(data.name))
        if data.driver and data.driver != "local":
            validate_network_driver(data.driver)
            parts.append(f"--driver {shlex.quote(data.driver)}")
        node = await self._runner.get_target(data.node_id)
        cmd = self._runner.build_command(node, " ".join(parts))
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        volume_name = stdout.strip() or data.name or ""
        audit.info(
            "docker.volumes.create",
            node_id=str(data.node_id),
            name=volume_name,
        )
        if self._audit:
            await self._audit.log(
                action="docker.volumes.create",
                node_id=data.node_id,
                details={"name": volume_name},
            )
        return volume_name

    async def inspect_volume(
        self, node_id: UUID, volume_name: str
    ) -> DockerVolumeInspectDTO:
        """Inspect a Docker volume."""
        validate_volume_name(volume_name)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(
            node, f"volume inspect {shlex.quote(volume_name)}"
        )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_array(stdout)
        if not items:
            raise_for_docker_error(f"Volume {volume_name!r} not found", 1)
        vol = items[0]
        labels_raw = vol.get("Labels") or {}
        labels = (
            tuple((k, v) for k, v in labels_raw.items())
            if isinstance(labels_raw, dict)
            else ()
        )
        audit.info("docker.volumes.inspect", node_id=str(node_id), name=volume_name)
        return DockerVolumeInspectDTO(
            name=json_string(vol, "Name"),
            driver=json_string(vol, "Driver"),
            mountpoint=json_string(vol, "Mountpoint"),
            labels=labels,
        )

    async def remove_volume(self, node_id: UUID, volume_name: str) -> None:
        """Remove a Docker volume."""
        validate_volume_name(volume_name)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, f"volume rm {shlex.quote(volume_name)}")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info("docker.volumes.remove", node_id=str(node_id), name=volume_name)
        if self._audit:
            await self._audit.log(
                action="docker.volumes.remove",
                node_id=node_id,
                details={"name": volume_name},
            )

    async def prune_volumes(self, node_id: UUID) -> str:
        """Prune unused Docker volumes and return the output."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "volume prune -f")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info("docker.volumes.prune", node_id=str(node_id))
        if self._audit:
            await self._audit.log(
                action="docker.volumes.prune", node_id=node_id, details={}
            )
        return stdout.strip()

    async def prune_networks(self, node_id: UUID) -> str:
        """Prune unused Docker networks and return the output."""
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "network prune -f")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info("docker.networks.prune", node_id=str(node_id))
        if self._audit:
            await self._audit.log(
                action="docker.networks.prune", node_id=node_id, details={}
            )
        return stdout.strip()
