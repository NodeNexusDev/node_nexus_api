"""Parallel command execution use case for multiple nodes."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.application.dto.node_connection import NodeConnectionDTO
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.command_history import CommandHistoryWriter
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.node_reader import NodeConnectionReader
    from app.application.ports.remote_command import RemoteConnectorFactory

from app.application.command_policy import command_fingerprint
from app.application.dto.bulk_node_operation import BulkValidateCredentialsResultDTO
from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    BulkCommandResultDTO,
    CommandExecutionDTO,
)
from app.application.dto.command_history import CommandHistoryCreateDTO
from app.application.policies.output import bound_output
from app.application.services._target_resolver import resolve_targets
from app.application.services.ssh_executor import (
    build_ssh_connector,
    execute_ssh,
)
from app.application.types import JsonObject
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError

audit = structlog.get_logger("audit")


class NodeBulkCommandService:
    """Resolve targets and execute one command concurrently."""

    _DEFAULT_MAX_CONCURRENCY = 50

    def __init__(
        self,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        audit_service: AuditEventSink | None = None,
        history_writer: CommandHistoryWriter | None = None,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self._node_reader = node_reader
        self._credential_cipher = credential_cipher
        self._audit = audit_service
        self._connector_factory = connector_factory
        self._history_writer = history_writer
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(self, data: BulkCommandRequestDTO) -> BulkCommandResultDTO:
        """Execute a command on all matching nodes in parallel."""
        target_nodes = await self._resolve_targets(data)
        if not target_nodes:
            raise NodeNotFoundError("No nodes matched the given criteria")

        batch_id = uuid.uuid4()
        started_at = datetime.now(UTC)

        if self._audit:
            fingerprint = command_fingerprint(data.command)
            for node in target_nodes:
                await self._audit.log_required(
                    action="bulk_execute.requested",
                    node_id=node.id,
                    details={"command_fingerprint": fingerprint},
                )

        results = await asyncio.gather(
            *(self._execute_on_single_node(node, data.command) for node in target_nodes)
        )

        finished_at = datetime.now(UTC)

        if self._history_writer:
            await self._save_history(
                data.command, results, batch_id, started_at, finished_at
            )

        # Audit uses the request-scoped session and therefore remains outside
        # concurrent workers.
        for result in results:
            succeeded = result.exit_code == 0
            details: JsonObject = {
                "command": data.command,
                "exit_code": result.exit_code,
            }
            if not succeeded:
                details["error"] = result.stderr
            if self._audit:
                await self._audit.log(
                    action="bulk_execute" if succeeded else "bulk_execute_failed",
                    node_id=result.node_id,
                    details=details,
                )

        succeeded = sum(1 for result in results if result.exit_code == 0)
        return BulkCommandResultDTO(
            command=data.command,
            results=tuple(results),
            total=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
        )

    async def bulk_execute_command(
        self,
        data: BulkCommandRequestDTO,
    ) -> BulkCommandResultDTO:
        """Expose the stable node API use-case name."""
        return await self.execute(data)

    async def validate_credentials_bulk(
        self,
        node_ids: list[uuid.UUID] | None = None,
        tags: list[str] | None = None,
    ) -> list[BulkValidateCredentialsResultDTO]:
        """Validate SSH credentials for multiple existing nodes."""
        nodes = await resolve_targets(self._node_reader, node_ids=node_ids, tags=tags)

        async def _validate_one(
            node: NodeConnectionDTO,
        ) -> BulkValidateCredentialsResultDTO:
            try:
                connector = build_ssh_connector(
                    node, self._credential_cipher, self._connector_factory
                )
                async with connector:
                    await connector.execute_command("echo ok")
                return BulkValidateCredentialsResultDTO(
                    node_id=node.id,
                    node_name=node.name,
                    status="success",
                    message="Credentials valid",
                )
            except Exception as exc:
                return BulkValidateCredentialsResultDTO(
                    node_id=node.id,
                    node_name=node.name,
                    status="error",
                    message=str(exc),
                )

        return list(await asyncio.gather(*(_validate_one(node) for node in nodes)))

    async def _resolve_targets(
        self, data: BulkCommandRequestDTO
    ) -> list[NodeConnectionDTO]:
        """Resolve target nodes from IDs and tags before concurrent work."""
        return await resolve_targets(
            self._node_reader,
            node_ids=data.node_ids,
            tags=data.tags,
        )

    async def _execute_on_single_node(
        self,
        node: NodeConnectionDTO,
        command: str,
    ) -> CommandExecutionDTO:
        """Execute on one node and always return a result."""
        async with self._semaphore:
            connector = build_ssh_connector(
                node, self._credential_cipher, self._connector_factory
            )

            try:
                result = await execute_ssh(connector, command)
                audit.info("node.bulk.executed", node_id=str(node.id), command=command)
                return CommandExecutionDTO(
                    node_id=node.id,
                    node_name=node.name,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exit_code,
                )
            except ConnectionFailedError as exc:
                audit.error(
                    "node.bulk.execute.failed",
                    node_id=str(node.id),
                    command=command,
                    error=str(exc),
                )
                return self._error_result(node, exc)
            except Exception as exc:
                audit.error(
                    "node.bulk.execute.unexpected_error",
                    node_id=str(node.id),
                    command=command,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return self._error_result(node, exc)

    @staticmethod
    def _error_result(node: NodeConnectionDTO, exc: Exception) -> CommandExecutionDTO:
        return CommandExecutionDTO(
            node_id=node.id,
            node_name=node.name,
            stdout="",
            stderr=str(exc),
            exit_code=1,
        )

    async def _save_history(
        self,
        command: str,
        results: Sequence[CommandExecutionDTO],
        batch_id: uuid.UUID,
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        """Persist each node execution result as a history record."""
        writer = self._history_writer
        if writer is None:
            return
        fingerprint = command_fingerprint(command)

        async def _save_single(result: CommandExecutionDTO) -> None:
            bounded = bound_output(result.stdout)
            stderr_bounded = bound_output(result.stderr)
            await writer.save(
                CommandHistoryCreateDTO(
                    node_id=result.node_id,
                    command_fingerprint=fingerprint,
                    exit_code=result.exit_code,
                    stdout=bounded.value,
                    stderr=stderr_bounded.value,
                    stdout_bytes=bounded.original_bytes,
                    stderr_bytes=stderr_bounded.original_bytes,
                    truncated=bounded.truncated or stderr_bounded.truncated,
                    batch_id=batch_id,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )

        await asyncio.gather(*(_save_single(result) for result in results))
