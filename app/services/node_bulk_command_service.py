"""Parallel command execution use case for multiple nodes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.application.dto.node_connection import NodeConnectionDTO
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory
    from app.services.audit_service import AuditService

from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    BulkCommandResultDTO,
    CommandExecutionDTO,
)
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.core.ssh_utils import get_connector_factory

audit = structlog.get_logger("audit")


class NodeBulkCommandService:
    """Resolve targets and execute one command concurrently."""

    def __init__(
        self,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
        audit_service: AuditService | None = None,
        connector_factory: ConnectorFactory | None = None,
    ) -> None:
        self._node_reader = node_reader
        self._credential_cipher = credential_cipher
        self._audit = audit_service
        self._connector_factory = connector_factory

    async def execute(self, data: BulkCommandRequestDTO) -> BulkCommandResultDTO:
        """Execute a command on all matching nodes in parallel."""
        target_nodes = await self._resolve_targets(data)
        if not target_nodes:
            raise NodeNotFoundError("No nodes matched the given criteria")

        results = await asyncio.gather(
            *(self._execute_on_single_node(node, data.command) for node in target_nodes)
        )

        # Audit uses the request-scoped session and therefore remains outside
        # concurrent workers.
        for result in results:
            succeeded = result.exit_code == 0
            details: dict[str, Any] = {
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
        connector = get_connector_factory(self._connector_factory).create_ssh(
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
