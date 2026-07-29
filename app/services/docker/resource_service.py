"""Docker network and volume use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink

import structlog

from app.application.dto.docker import DockerNetworkDTO, DockerVolumeDTO
from app.services.docker.command_runner import DockerCommandRunner
from app.services.docker.error_mapper import raise_for_docker_error
from app.services.docker.parsers import parse_json_lines

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
    ) -> list[dict]:
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
                id=item["ID"],
                name=item["Name"],
                driver=item["Driver"],
                scope=item["Scope"],
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
            DockerVolumeDTO(driver=item["Driver"], name=item["Name"]) for item in items
        ]
