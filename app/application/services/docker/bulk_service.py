"""Docker bulk orchestration."""

from __future__ import annotations

import asyncio
import shlex
import uuid
from typing import TYPE_CHECKING

import structlog

from app.application.dto.docker import (
    BulkDockerNodeResultDTO,
    BulkDockerPullResultDTO,
    BulkDockerPullResultsDTO,
    BulkDockerResultDTO,
)
from app.application.services.docker.command_runner import DockerCommandRunner
from app.core.docker_validation import validate_container_id
from app.core.exceptions import DockerError, NodeNotFoundError

audit = structlog.get_logger("audit")

if TYPE_CHECKING:
    from app.application.dto.node_connection import NodeConnectionDTO


class DockerBulkService:
    """Preload targets, run remote workers, and preserve result order."""

    def __init__(self, runner: DockerCommandRunner) -> None:
        self._runner = runner

    async def _prepare(
        self, node_ids: list[uuid.UUID]
    ) -> tuple[
        list[tuple[int, str, NodeConnectionDTO]],
        dict[int, BulkDockerNodeResultDTO],
    ]:
        prepared: list[tuple[int, str, NodeConnectionDTO]] = []
        errors: dict[int, BulkDockerNodeResultDTO] = {}
        for index, node_id in enumerate(node_ids):
            try:
                node = await self._runner.get_target(node_id)
                prepared.append((index, str(node_id), node))
            except NodeNotFoundError:
                errors[index] = BulkDockerNodeResultDTO(
                    node_id=str(node_id),
                    node_name="unknown",
                    status="error",
                    error="Node not found",
                )
            except (ValueError, DockerError) as exc:
                errors[index] = BulkDockerNodeResultDTO(
                    node_id=str(node_id),
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )
        return prepared, errors

    async def _resolve_node_ids(
        self, node_ids: list[uuid.UUID], node_tags: list[str]
    ) -> list[uuid.UUID]:
        """Merge explicit node_ids with tag-resolved ids, deduplicated.

        Uses union (OR) logic: nodes matching either node_ids OR tags are
        included. This expands the target set for docker bulk operations.

        For node bulk operations with intersection (AND) logic, see
        _target_resolver.resolve_targets().
        """
        if not node_tags:
            return list(node_ids)
        try:
            tag_nodes = await self._runner.get_targets_by_tags(list(node_tags))
        except Exception as exc:
            audit.warning(
                "docker.bulk.resolve_tags.failed",
                tags=node_tags,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            tag_nodes = []
        tag_ids = [node.id for node in tag_nodes if node.connection_type == "docker"]
        merged = [*node_ids, *tag_ids]
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for node_id in merged:
            if node_id not in seen:
                seen.add(node_id)
                deduped.append(node_id)
        return deduped

    @staticmethod
    def _finalize(
        prepared: list[tuple[int, str, NodeConnectionDTO]],
        errors: dict[int, BulkDockerNodeResultDTO],
        remote_results: list[BulkDockerNodeResultDTO],
    ) -> list[BulkDockerNodeResultDTO]:
        for (index, _, _), result in zip(prepared, remote_results, strict=True):
            errors[index] = result
        return [errors[i] for i in sorted(errors)]

    async def bulk_container_action(
        self,
        node_ids: list[uuid.UUID],
        container_id: str,
        action: str,
        timeout: int | None = None,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        validated_id = validate_container_id(container_id)
        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerNodeResultDTO:
            try:
                if action == "start":
                    args = f"start {validated_id}"
                elif action in {"stop", "restart"}:
                    timeout_val = timeout if timeout is not None else 10
                    args = f"{action} -t {timeout_val} {validated_id}"
                elif action == "remove":
                    args = f"rm -f {validated_id}"
                else:
                    raise DockerError(f"Unknown action: {action}")
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(node, cmd)
                if exit_code != 0 and stderr:
                    return BulkDockerNodeResultDTO(
                        node_id=node_id_str,
                        node_name=node.name,
                        status="error",
                        error=stderr.strip(),
                    )
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success",
                    output=stdout.strip(),
                )
            except Exception as exc:
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(
                *(worker(node_id_str, node) for _, node_id_str, node in prepared)
            )
        )
        results = self._finalize(prepared, errors, remote)
        return self._response(action, validated_id, results)

    async def bulk_exec(
        self,
        node_ids: list[uuid.UUID],
        container_id: str,
        command: str,
        timeout: int = 30,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        validated_id = validate_container_id(container_id)
        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerNodeResultDTO:
            try:
                args = f"exec {validated_id} sh -c {shlex.quote(command)}"
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(
                    node, cmd, timeout
                )
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success" if exit_code == 0 else "error",
                    output=stdout.strip(),
                    error=stderr.strip() if exit_code != 0 else "",
                )
            except Exception as exc:
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(
                *(worker(node_id_str, node) for _, node_id_str, node in prepared)
            )
        )
        results = self._finalize(prepared, errors, remote)
        return self._response("exec", validated_id, results)

    @staticmethod
    def _response(
        action: str,
        container_id: str,
        results: list[BulkDockerNodeResultDTO],
    ) -> BulkDockerResultDTO:
        succeeded = sum(result.status == "success" for result in results)
        failed = len(results) - succeeded
        audit.info(
            f"docker.bulk.{action}",
            container_id=container_id,
            total=len(results),
            succeeded=succeeded,
            failed=failed,
        )
        return BulkDockerResultDTO(
            action=action,
            results=tuple(results),
            total=len(results),
            succeeded=succeeded,
            failed=failed,
        )

    async def bulk_pull_image(
        self,
        node_ids: list[uuid.UUID],
        image: str,
        timeout: int | None = None,
        node_tags: list[str] | None = None,
    ) -> BulkDockerPullResultsDTO:
        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerPullResultDTO:
            try:
                args = f"pull {image}"
                cmd = self._runner.build_command(node, args)
                exec_timeout = timeout if timeout is not None else 300
                stdout, stderr, exit_code = await self._runner.execute(
                    node, cmd, exec_timeout
                )
                if exit_code != 0 and stderr:
                    return BulkDockerPullResultDTO(
                        node_id=node_id_str,
                        node_name=node.name,
                        status="error",
                        error=stderr.strip(),
                    )
                return BulkDockerPullResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success",
                    output=stdout.strip(),
                )
            except Exception as exc:
                return BulkDockerPullResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(
                *(worker(node_id_str, node) for _, node_id_str, node in prepared)
            )
        )

        merged: dict[int, BulkDockerPullResultDTO] = {}
        for idx, err in errors.items():
            merged[idx] = BulkDockerPullResultDTO(
                node_id=err.node_id,
                node_name=err.node_name,
                status=err.status,
                output=err.output,
                error=err.error,
            )
        for (index, _, _), result in zip(prepared, remote, strict=True):
            merged[index] = result

        all_results = [merged[i] for i in sorted(merged)]
        pull_results = [
            BulkDockerPullResultDTO(
                node_id=r.node_id,
                node_name=r.node_name,
                status=r.status,
                output=r.output,
                error=r.error,
            )
            for r in all_results
        ]

        succeeded = sum(1 for r in pull_results if r.status == "success")
        failed = len(pull_results) - succeeded

        audit.info(
            "docker.bulk.pull",
            image=image,
            total=len(pull_results),
            succeeded=succeeded,
            failed=failed,
        )

        return BulkDockerPullResultsDTO(
            results=tuple(pull_results),
            total=len(pull_results),
            succeeded=succeeded,
            failed=failed,
        )

    async def bulk_image_remove(
        self,
        node_ids: list[uuid.UUID],
        image_id: str,
        node_tags: list[str] | None = None,
    ) -> BulkDockerPullResultsDTO:
        """Remove Docker image on multiple nodes."""

        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerPullResultDTO:
            try:
                args = f"rmi -f {image_id}"
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(node, cmd)
                if exit_code != 0 and stderr:
                    return BulkDockerPullResultDTO(
                        node_id=node_id_str,
                        node_name=node.name,
                        status="error",
                        error=stderr.strip(),
                    )
                return BulkDockerPullResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success",
                    output=stdout.strip(),
                )
            except Exception as exc:
                return BulkDockerPullResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(
                *(worker(node_id_str, node) for _, node_id_str, node in prepared)
            )
        )

        merged: dict[int, BulkDockerPullResultDTO] = {}
        for idx, err in errors.items():
            merged[idx] = BulkDockerPullResultDTO(
                node_id=err.node_id,
                node_name=err.node_name,
                status=err.status,
                output=err.output,
                error=err.error,
            )
        for (index, _, _), result in zip(prepared, remote, strict=True):
            merged[index] = result

        all_results = [merged[i] for i in sorted(merged)]
        pull_results = [
            BulkDockerPullResultDTO(
                node_id=r.node_id,
                node_name=r.node_name,
                status=r.status,
                output=r.output,
                error=r.error,
            )
            for r in all_results
        ]

        succeeded = sum(1 for r in pull_results if r.status == "success")
        failed = len(pull_results) - succeeded

        audit.info(
            "docker.bulk.image.remove",
            image_id=image_id,
            total=len(pull_results),
            succeeded=succeeded,
            failed=failed,
        )

        return BulkDockerPullResultsDTO(
            results=tuple(pull_results),
            total=len(pull_results),
            succeeded=succeeded,
            failed=failed,
        )

    async def bulk_image_build(
        self,
        node_ids: list[uuid.UUID],
        dockerfile: str,
        tag: str,
        build_args: dict[str, str] | None = None,
        no_cache: bool = False,
        timeout: int | None = None,
        node_tags: list[str] | None = None,
    ) -> BulkDockerPullResultsDTO:
        """Build Docker image on multiple nodes."""

        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerPullResultDTO:
            try:
                build_args_str = ""
                if build_args:
                    for key, value in build_args.items():
                        build_args_str += f" --build-arg {key}={value}"

                cache_flag = " --no-cache" if no_cache else ""
                args = f"build{cache_flag}{build_args_str} -t {tag} -"
                base_cmd = self._runner.build_command(node, args)
                quoted_stdin = shlex.quote(dockerfile)
                cmd = f"printf %s {quoted_stdin} | {base_cmd}"
                exec_timeout = timeout if timeout is not None else 300
                stdout, stderr, exit_code = await self._runner.execute(
                    node, cmd, exec_timeout
                )
                if exit_code != 0 and stderr:
                    return BulkDockerPullResultDTO(
                        node_id=node_id_str,
                        node_name=node.name,
                        status="error",
                        error=stderr.strip(),
                    )
                return BulkDockerPullResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success",
                    output=stdout.strip(),
                )
            except Exception as exc:
                return BulkDockerPullResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(
                *(worker(node_id_str, node) for _, node_id_str, node in prepared)
            )
        )

        merged: dict[int, BulkDockerPullResultDTO] = {}
        for idx, err in errors.items():
            merged[idx] = BulkDockerPullResultDTO(
                node_id=err.node_id,
                node_name=err.node_name,
                status=err.status,
                output=err.output,
                error=err.error,
            )
        for (index, _, _), result in zip(prepared, remote, strict=True):
            merged[index] = result

        all_results = [merged[i] for i in sorted(merged)]
        pull_results = [
            BulkDockerPullResultDTO(
                node_id=r.node_id,
                node_name=r.node_name,
                status=r.status,
                output=r.output,
                error=r.error,
            )
            for r in all_results
        ]

        succeeded = sum(1 for r in pull_results if r.status == "success")
        failed = len(pull_results) - succeeded

        audit.info(
            "docker.bulk.image.build",
            tag=tag,
            total=len(pull_results),
            succeeded=succeeded,
            failed=failed,
        )

        return BulkDockerPullResultsDTO(
            results=tuple(pull_results),
            total=len(pull_results),
            succeeded=succeeded,
            failed=failed,
        )

    # ── Bulk inspect / logs / stats ────────────────────────────────────────

    async def bulk_inspect(
        self,
        node_ids: list[uuid.UUID],
        container_id: str,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        """Inspect a container across multiple nodes."""
        validated_id = validate_container_id(container_id)
        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerNodeResultDTO:
            try:
                args = f"inspect {validated_id}"
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(node, cmd)
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success" if exit_code == 0 else "error",
                    output=stdout.strip(),
                    error=stderr.strip() if exit_code != 0 else "",
                )
            except Exception as exc:
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(*(worker(nid, node) for _, nid, node in prepared))
        )
        results = self._finalize(prepared, errors, remote)
        return self._response("inspect", validated_id, results)

    async def bulk_logs(
        self,
        node_ids: list[uuid.UUID],
        container_id: str,
        tail: int = 100,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        """Get logs from a container across multiple nodes."""
        validated_id = validate_container_id(container_id)
        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerNodeResultDTO:
            try:
                args = f"logs --tail {tail} {validated_id}"
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(node, cmd)
                output = stdout.strip() or stderr.strip()
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success" if exit_code == 0 else "error",
                    output=output,
                    error=stderr.strip() if exit_code != 0 and stderr else "",
                )
            except Exception as exc:
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(*(worker(nid, node) for _, nid, node in prepared))
        )
        results = self._finalize(prepared, errors, remote)
        return self._response("logs", validated_id, results)

    async def bulk_stats(
        self,
        node_ids: list[uuid.UUID],
        container_id: str,
        node_tags: list[str] | None = None,
    ) -> BulkDockerResultDTO:
        """Get stats from a container across multiple nodes."""
        validated_id = validate_container_id(container_id)
        resolved_ids = await self._resolve_node_ids(node_ids, list(node_tags or []))
        prepared, errors = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerNodeResultDTO:
            try:
                args = f"stats --no-stream --format '{{{{json .}}}}' {validated_id}"
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(node, cmd)
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success" if exit_code == 0 else "error",
                    output=stdout.strip(),
                    error=stderr.strip() if exit_code != 0 else "",
                )
            except Exception as exc:
                return BulkDockerNodeResultDTO(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )

        remote = list(
            await asyncio.gather(*(worker(nid, node) for _, nid, node in prepared))
        )
        results = self._finalize(prepared, errors, remote)
        return self._response("stats", validated_id, results)
