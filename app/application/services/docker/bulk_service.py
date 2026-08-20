"""Docker bulk orchestration."""

from __future__ import annotations

import asyncio
import shlex
import uuid
from typing import TYPE_CHECKING

import structlog

from app.application.dto.docker import BulkDockerNodeResultDTO, BulkDockerResultDTO
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
        list[BulkDockerNodeResultDTO | None],
    ]:
        prepared: list[tuple[int, str, NodeConnectionDTO]] = []
        results: list[BulkDockerNodeResultDTO | None] = [None] * len(node_ids)
        for index, node_id in enumerate(node_ids):
            try:
                node = await self._runner.get_target(node_id)
                prepared.append((index, str(node_id), node))
            except NodeNotFoundError:
                results[index] = BulkDockerNodeResultDTO(
                    node_id=str(node_id),
                    node_name="unknown",
                    status="error",
                    error="Node not found",
                )
            except (ValueError, DockerError) as exc:
                results[index] = BulkDockerNodeResultDTO(
                    node_id=str(node_id),
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )
        return prepared, results

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
        slots: list[BulkDockerNodeResultDTO | None],
        remote_results: list[BulkDockerNodeResultDTO],
    ) -> list[BulkDockerNodeResultDTO]:
        for (index, _, _), result in zip(prepared, remote_results, strict=True):
            slots[index] = result
        return [result for result in slots if result is not None]

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
        prepared, slots = await self._prepare(resolved_ids)

        async def worker(
            node_id_str: str, node: NodeConnectionDTO
        ) -> BulkDockerNodeResultDTO:
            try:
                if action == "start":
                    args = f"start {validated_id}"
                elif action in {"stop", "restart"}:
                    timeout_val = timeout if timeout is not None else 10
                    args = f"{action} -t {timeout_val} {validated_id}"
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
        results = self._finalize(prepared, slots, remote)
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
        prepared, slots = await self._prepare(resolved_ids)

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
        results = self._finalize(prepared, slots, remote)
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
