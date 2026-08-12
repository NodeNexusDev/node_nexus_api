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
from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    BulkCommandResultDTO,
    CommandExecutionDTO,
)
from app.application.dto.command_history import CommandHistoryCreateDTO
from app.application.policies.output import bound_output
from app.application.types import JsonObject
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError

audit = structlog.get_logger("audit")


class NodeBulkCommandService:
    """Resolve targets and execute one command concurrently."""

    def __init__(
        self,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        audit_service: AuditEventSink | None = None,
        history_writer: CommandHistoryWriter | None = None,
    ) -> None:
        self._node_reader = node_reader
        self._credential_cipher = credential_cipher
        self._audit = audit_service
        self._connector_factory = connector_factory
        self._history_writer = history_writer

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

    async def _resolve_targets(
        self, data: BulkCommandRequestDTO
    ) -> list[NodeConnectionDTO]:
        """Resolve target nodes from IDs and tags before concurrent work."""
        nodes_by_ids = None
        if data.node_ids:
            nodes_by_ids = await self._node_reader.get_connections_by_ids(
                list(data.node_ids)
            )

        nodes_by_tags = None
        if data.tags:
            nodes_by_tags = await self._node_reader.get_connections_by_tags(
                list(data.tags)
            )

        if nodes_by_ids is not None and nodes_by_tags is not None:
            tag_ids = {node.id for node in nodes_by_tags}
            return [node for node in nodes_by_ids if node.id in tag_ids]
        if nodes_by_ids is not None:
            return nodes_by_ids
        return nodes_by_tags or []

    async def _execute_on_single_node(
        self,
        node: NodeConnectionDTO,
        command: str,
    ) -> CommandExecutionDTO:
        """Execute on one node and always return a result."""
        connector = self._connector_factory.create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=self._credential_cipher.decrypt(node.password),
            ssh_key=self._credential_cipher.decrypt(node.ssh_key),
        )

        try:
            async with connector:
                stdout, stderr, exit_code = await connector.execute_command(command)
            audit.info("node.bulk.executed", node_id=str(node.id), command=command)
            return CommandExecutionDTO(
                node_id=node.id,
                node_name=node.name,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
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
        if self._history_writer is None:
            return
        fingerprint = command_fingerprint(command)
        for result in results:
            bounded = bound_output(result.stdout)
            stderr_bounded = bound_output(result.stderr)
            await self._history_writer.save(
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
