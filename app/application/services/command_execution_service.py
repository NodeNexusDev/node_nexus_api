"""Command execution application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.application.command_policy import command_fingerprint
from app.application.dto.command_execution import CommandResultDTO
from app.application.dto.command_history import CommandHistoryCreateDTO
from app.application.dto.command_management import CommandExecuteRequestDTO
from app.application.policies.output import bound_output
from app.application.types import JsonObject
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
)
from app.core.template import render_command

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.command_history import CommandHistoryWriter
    from app.application.ports.command_reader import CommandTemplateReader
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.node_reader import NodeConnectionReader
    from app.application.ports.remote_command import RemoteConnectorFactory

audit = structlog.get_logger("audit")


class CommandExecutionService:
    """Render and execute stored command templates on remote nodes."""

    def __init__(
        self,
        command_reader: CommandTemplateReader,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        audit_service: AuditEventSink | None = None,
        history_writer: CommandHistoryWriter | None = None,
    ) -> None:
        self._command_reader = command_reader
        self._node_reader = node_reader
        self._credential_cipher = credential_cipher
        self._connector_factory = connector_factory
        self._audit = audit_service
        self._history_writer = history_writer

    async def _log(
        self,
        action: str,
        node_id: UUID,
        details: JsonObject,
    ) -> None:
        if self._audit:
            await self._audit.log(action=action, node_id=node_id, details=details)

    async def execute_command(
        self, command_id: UUID, data: CommandExecuteRequestDTO
    ) -> CommandResultDTO:
        command = await self._command_reader.get_template(command_id)
        if command is None:
            raise CommandNotFoundError(f"Command {command_id} not found")
        rendered = render_command(
            command.command,
            list(command.parameters or ()),
            dict(data.params),
        )

        node = await self._node_reader.get_connection(data.node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {data.node_id} not found")
        connector = self._connector_factory.create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=self._credential_cipher.decrypt(node.password),
            ssh_key=self._credential_cipher.decrypt(node.ssh_key),
        )

        try:
            from datetime import UTC, datetime

            started_at = datetime.now(UTC)
            async with connector:
                stdout, stderr, exit_code = await connector.execute_command(rendered)
            finished_at = datetime.now(UTC)
            bounded_stdout = bound_output(stdout)
            bounded_stderr = bound_output(stderr)
            audit.info(
                "command.executed",
                command_id=str(command_id),
                node_id=str(data.node_id),
                exit_code=exit_code,
            )
            await self._log(
                "execute",
                data.node_id,
                {"command_id": str(command_id), "exit_code": exit_code},
            )
            if self._history_writer is not None:
                await self._history_writer.save(
                    CommandHistoryCreateDTO(
                        node_id=data.node_id,
                        command_id=command_id,
                        command_fingerprint=command_fingerprint(rendered),
                        exit_code=exit_code,
                        stdout=bounded_stdout.value,
                        stderr=bounded_stderr.value,
                        stdout_bytes=bounded_stdout.original_bytes,
                        stderr_bytes=bounded_stderr.original_bytes,
                        truncated=bounded_stdout.truncated or bounded_stderr.truncated,
                        started_at=started_at,
                        finished_at=finished_at,
                    )
                )
            return CommandResultDTO(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )
        except Exception as exc:
            audit.error(
                "command.execute.failed",
                command_id=str(command_id),
                node_id=str(data.node_id),
                error=str(exc),
            )
            await self._log(
                "execute_failed",
                data.node_id,
                {"command_id": str(command_id), "error": str(exc)},
            )
            raise ConnectionFailedError(
                f"Failed to execute command on node {data.node_id}: {exc}"
            ) from exc
