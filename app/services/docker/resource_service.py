"""Docker network and volume use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

if TYPE_CHECKING:
    from app.services.audit_service import AuditService

import structlog
from pydantic import BaseModel

from app.schemas.docker import DockerNetwork, DockerVolume
from app.services.docker.command_runner import DockerCommandRunner
from app.services.docker.error_mapper import raise_for_docker_error
from app.services.docker.parsers import parse_json_lines

audit = structlog.get_logger("audit")
ResourceT = TypeVar("ResourceT", bound=BaseModel)


class DockerResourceService:
    """Network and volume listing operations."""

    def __init__(
        self, runner: DockerCommandRunner, audit_service: AuditService | None = None
    ) -> None:
        self._runner = runner
        self._audit = audit_service

    async def _list(
        self,
        node_id: UUID,
        docker_args: str,
        event: str,
        model: type[ResourceT],
    ) -> list[ResourceT]:
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
        return [model.model_validate(item) for item in items]

    async def list_networks(self, node_id: UUID) -> list[DockerNetwork]:
        return await self._list(
            node_id,
            "network ls --format '{{json .}}'",
            "docker.networks.list",
            DockerNetwork,
        )

    async def list_volumes(self, node_id: UUID) -> list[DockerVolume]:
        return await self._list(
            node_id,
            "volume ls --format '{{json .}}'",
            "docker.volumes.list",
            DockerVolume,
        )
