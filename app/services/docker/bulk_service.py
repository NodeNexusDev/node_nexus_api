"""Docker bulk orchestration."""

import asyncio
import shlex
import uuid
from typing import Any

import structlog

from app.core.docker_validation import validate_container_id
from app.core.exceptions import DockerError, NodeNotFoundError
from app.schemas.docker import BulkDockerNodeResult, BulkDockerResponse
from app.services.docker.command_runner import DockerCommandRunner

audit = structlog.get_logger("audit")


class DockerBulkService:
    """Preload targets, run remote workers, and preserve result order."""

    def __init__(self, runner: DockerCommandRunner) -> None:
        self._runner = runner

    async def _prepare(
        self, node_ids: list[str]
    ) -> tuple[
        list[tuple[int, str, Any]],
        list[BulkDockerNodeResult | None],
    ]:
        prepared: list[tuple[int, str, Any]] = []
        results: list[BulkDockerNodeResult | None] = [None] * len(node_ids)
        for index, node_id_str in enumerate(node_ids):
            try:
                node = await self._runner.get_target(uuid.UUID(node_id_str))
                prepared.append((index, node_id_str, node))
            except NodeNotFoundError:
                results[index] = BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error="Node not found",
                )
            except (ValueError, DockerError) as exc:
                results[index] = BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name="unknown",
                    status="error",
                    error=str(exc),
                )
        return prepared, results

    @staticmethod
    def _finalize(
        prepared: list[tuple[int, str, Any]],
        slots: list[BulkDockerNodeResult | None],
        remote_results: list[BulkDockerNodeResult],
    ) -> list[BulkDockerNodeResult]:
        for (index, _, _), result in zip(prepared, remote_results, strict=True):
            slots[index] = result
        return [result for result in slots if result is not None]

    async def bulk_container_action(
        self,
        node_ids: list[str],
        container_id: str,
        action: str,
        timeout: int | None = None,
    ) -> BulkDockerResponse:
        validated_id = validate_container_id(container_id)
        prepared, slots = await self._prepare(node_ids)

        async def worker(node_id_str: str, node: Any) -> BulkDockerNodeResult:
            try:
                if action == "start":
                    args = f"start {validated_id}"
                elif action in {"stop", "restart"}:
                    args = f"{action} -t {timeout or 10} {validated_id}"
                else:
                    raise DockerError(f"Unknown action: {action}")
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(node, cmd)
                if exit_code != 0 and stderr:
                    return BulkDockerNodeResult(
                        node_id=node_id_str,
                        node_name=node.name,
                        status="error",
                        error=stderr.strip(),
                    )
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success",
                    output=stdout.strip(),
                )
            except Exception as exc:
                return BulkDockerNodeResult(
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
        self, node_ids: list[str], container_id: str, command: str, timeout: int = 30
    ) -> BulkDockerResponse:
        validated_id = validate_container_id(container_id)
        prepared, slots = await self._prepare(node_ids)

        async def worker(node_id_str: str, node: Any) -> BulkDockerNodeResult:
            try:
                args = f"exec {validated_id} sh -c {shlex.quote(command)}"
                cmd = self._runner.build_command(node, args)
                stdout, stderr, exit_code = await self._runner.execute(
                    node, cmd, timeout
                )
                return BulkDockerNodeResult(
                    node_id=node_id_str,
                    node_name=node.name,
                    status="success" if exit_code == 0 else "error",
                    output=stdout.strip(),
                    error=stderr.strip() if exit_code != 0 else "",
                )
            except Exception as exc:
                return BulkDockerNodeResult(
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
        results: list[BulkDockerNodeResult],
    ) -> BulkDockerResponse:
        succeeded = sum(result.status == "success" for result in results)
        failed = len(results) - succeeded
        audit.info(
            f"docker.bulk.{action}",
            container_id=container_id,
            total=len(results),
            succeeded=succeeded,
            failed=failed,
        )
        return BulkDockerResponse(
            action=action,
            results=results,
            total=len(results),
            succeeded=succeeded,
            failed=failed,
        )
