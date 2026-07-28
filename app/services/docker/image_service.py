"""Docker image use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.services.audit_service import AuditService

import structlog

from app.core.docker_validation import validate_image_name
from app.core.exceptions import ConnectionFailedError
from app.schemas.docker import DockerImage, DockerPullResult
from app.services.docker.command_runner import DockerCommandRunner
from app.services.docker.error_mapper import raise_for_docker_error
from app.services.docker.parsers import parse_json_lines

audit = structlog.get_logger("audit")


class DockerImageService:
    """Image operations composed over the shared command runner."""

    def __init__(
        self, runner: DockerCommandRunner, audit_service: AuditService | None = None
    ) -> None:
        self._runner = runner
        self._audit = audit_service

    async def list_images(self, node_id: UUID) -> list[DockerImage]:
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, "images --format '{{json .}}'")
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_lines(stdout)
        audit.info("docker.images.list", node_id=str(node_id), count=len(items))
        if self._audit:
            await self._audit.log(
                action="docker.images.list",
                node_id=node_id,
                details={"count": len(items)},
            )
        return [DockerImage.model_validate(item) for item in items]

    async def pull_image(
        self, node_id: UUID, image: str, *, timeout: int = 300
    ) -> DockerPullResult:
        validated = validate_image_name(image)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, f"pull {validated}")
        try:
            stdout, stderr, exit_code = await self._runner.execute(node, cmd, timeout)
        except ConnectionFailedError as exc:
            audit.error(
                "docker.image.pull.failed",
                node_id=str(node_id),
                image=validated,
                error=str(exc),
            )
            if self._audit:
                await self._audit.log(
                    action="docker.image.pull",
                    node_id=node_id,
                    details={"image": validated, "success": False},
                )
            return DockerPullResult(image=validated, output=str(exc), success=False)
        raise_for_docker_error(stderr, exit_code)
        success = exit_code == 0
        output = stdout if success else stderr
        audit.info(
            "docker.image.pull.ok" if success else "docker.image.pull.failed",
            node_id=str(node_id),
            image=validated,
        )
        if self._audit:
            await self._audit.log(
                action="docker.image.pull",
                node_id=node_id,
                details={"image": validated, "success": success},
            )
        return DockerPullResult(image=validated, output=output, success=success)
