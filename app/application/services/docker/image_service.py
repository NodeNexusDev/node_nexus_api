"""Docker image use cases."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink

import structlog

from app.application.dto.docker import (
    DockerImageBuildRequestDTO,
    DockerImageBuildResultDTO,
    DockerImageDTO,
    DockerImageInspectDTO,
    DockerImageTagRequestDTO,
    DockerImageTagResultDTO,
    DockerPullResultDTO,
)
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.application.services.docker.parsers import (
    json_string,
    parse_json_array,
    parse_json_lines,
)
from app.core.docker_validation import (
    validate_build_arg_key,
    validate_image_name,
    validate_image_tag,
)
from app.core.exceptions import ConnectionFailedError, DockerValidationError

audit = structlog.get_logger("audit")


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


class DockerImageService:
    """Image operations composed over the shared command runner."""

    def __init__(
        self,
        runner: DockerCommandRunner,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._runner = runner
        self._audit = audit_service

    async def list_images(self, node_id: UUID) -> list[DockerImageDTO]:
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
        return [
            DockerImageDTO(
                repository=json_string(item, "Repository"),
                tag=json_string(item, "Tag"),
                id=json_string(item, "ID"),
                size=json_string(item, "Size"),
                created_at=json_string(item, "CreatedAt"),
            )
            for item in items
        ]

    async def pull_image(
        self, node_id: UUID, image: str, *, timeout: int = 300
    ) -> DockerPullResultDTO:
        validated = validate_image_name(image)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, f"pull {validated}")
        if self._audit:
            await self._audit.log_required(
                action="docker.image.pull.requested",
                node_id=node_id,
                details={"image": validated},
            )
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
            return DockerPullResultDTO(image=validated, output=str(exc), success=False)
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
        return DockerPullResultDTO(image=validated, output=output, success=success)

    async def inspect_image(
        self, node_id: UUID, image_id: str
    ) -> DockerImageInspectDTO:
        """Inspect an image via ``docker inspect --type=image``."""
        validated = validate_image_tag(image_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(
            node,
            f"inspect --type=image {shlex.quote(validated)} --format '{{{{json .}}}}'",
        )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        items = parse_json_array(stdout)
        if not items:
            raise DockerValidationError(
                f"docker inspect produced no output for image {validated!r}"
            )
        data = items[0]
        repo_tags_raw = data.get("RepoTags")
        repo_tags = _string_tuple(repo_tags_raw)
        audit.info(
            "docker.image.inspect",
            node_id=str(node_id),
            image_id=validated,
        )
        if self._audit:
            await self._audit.log(
                action="docker.image.inspect",
                node_id=node_id,
                details={"image_id": validated},
            )
        return DockerImageInspectDTO(
            id=_string(data.get("Id")),
            repo_tags=repo_tags,
            size=_integer(data.get("Size")),
            created=_string(data.get("Created")),
            architecture=_string(data.get("Architecture")),
            os=_string(data.get("Os")),
        )

    async def remove_image(self, node_id: UUID, image_id: str) -> None:
        """Remove an image via ``docker rmi``."""
        validated = validate_image_tag(image_id)
        node = await self._runner.get_target(node_id)
        cmd = self._runner.build_command(node, f"rmi {shlex.quote(validated)}")
        if self._audit:
            await self._audit.log_required(
                action="docker.image.remove.requested",
                node_id=node_id,
                details={"image_id": validated},
            )
        _, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info("docker.image.remove", node_id=str(node_id), image_id=validated)
        if self._audit:
            await self._audit.log(
                action="docker.image.remove",
                node_id=node_id,
                details={"image_id": validated},
            )

    async def tag_image(
        self, request: DockerImageTagRequestDTO
    ) -> DockerImageTagResultDTO:
        """Tag an image via ``docker tag``."""
        validated_source = validate_image_tag(request.image_id)
        target = f"{request.repo}:{request.tag}"
        validated_target = validate_image_tag(target)
        node = await self._runner.get_target(request.node_id)
        cmd = self._runner.build_command(
            node, f"tag {shlex.quote(validated_source)} {shlex.quote(validated_target)}"
        )
        if self._audit:
            await self._audit.log_required(
                action="docker.image.tag.requested",
                node_id=request.node_id,
                details={"source": validated_source, "target": validated_target},
            )
        _, stderr, exit_code = await self._runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        audit.info(
            "docker.image.tag",
            node_id=str(request.node_id),
            source=validated_source,
            target=validated_target,
        )
        if self._audit:
            await self._audit.log(
                action="docker.image.tag",
                node_id=request.node_id,
                details={"source": validated_source, "target": validated_target},
            )
        return DockerImageTagResultDTO(source=validated_source, target=validated_target)

    @staticmethod
    def _build_build_command_args(request: DockerImageBuildRequestDTO) -> str:
        """Assemble the ``docker build`` argument string."""
        parts: list[str] = ["build"]
        parts.append(f"--tag {shlex.quote(request.tag)}")
        for key, value in request.build_args:
            parts.append(f"--build-arg {shlex.quote(f'{key}={value}')}")
        if request.no_cache:
            parts.append("--no-cache")
        parts.append("-")
        return " ".join(parts)

    async def build_image(
        self, request: DockerImageBuildRequestDTO
    ) -> DockerImageBuildResultDTO:
        """Build an image from a Dockerfile piped through stdin."""
        validated_tag = validate_image_tag(request.tag)
        validated_build_args: list[tuple[str, str]] = []
        for key, value in request.build_args:
            validated_build_args.append((validate_build_arg_key(key), value))
        normalized = DockerImageBuildRequestDTO(
            node_id=request.node_id,
            dockerfile=request.dockerfile,
            tag=validated_tag,
            build_args=tuple(validated_build_args),
            no_cache=request.no_cache,
        )
        node = await self._runner.get_target(request.node_id)
        quoted_stdin = shlex.quote(normalized.dockerfile)
        docker_args = self._build_build_command_args(normalized)
        base_cmd = self._runner.build_command(node, docker_args)
        cmd = f"printf %s {quoted_stdin} | {base_cmd}"
        if self._audit:
            await self._audit.log_required(
                action="docker.image.build.requested",
                node_id=request.node_id,
                details={"tag": validated_tag},
            )
        stdout, stderr, exit_code = await self._runner.execute(node, cmd, timeout=600)
        raise_for_docker_error(stderr, exit_code)
        image_id = ""
        for line in reversed(stdout.strip().splitlines()):
            stripped = line.strip()
            marker = "Successfully built "
            sha_marker = "sha256:"
            if stripped.startswith(marker):
                image_id = stripped[len(marker) :].strip()
                break
            if sha_marker in stripped:
                token = stripped.split()[-1]
                if token.startswith(sha_marker):
                    image_id = token
                    break
        output = stdout.strip()
        audit.info(
            "docker.image.build.ok",
            node_id=str(request.node_id),
            tag=validated_tag,
            image_id=image_id,
        )
        if self._audit:
            await self._audit.log(
                action="docker.image.build",
                node_id=request.node_id,
                details={"tag": validated_tag, "image_id": image_id},
            )
        return DockerImageBuildResultDTO(
            image_id=image_id, tag=validated_tag, output=output
        )
