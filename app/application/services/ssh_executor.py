"""Shared SSH execution helpers used by command services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from app.application.dto.command_history import CommandHistoryCreateDTO
    from app.application.dto.node_connection import NodeConnectionDTO
    from app.application.ports.command_history import CommandHistoryWriter
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.remote_command import (
        RemoteCommandSession,
        RemoteConnectorFactory,
    )

from app.application.command_policy import command_fingerprint
from app.application.policies.output import bound_output

audit = structlog.get_logger("audit")


@dataclass(frozen=True, slots=True)
class SshExecutionResult:
    """Raw result of a single SSH command execution."""

    stdout: str
    stderr: str
    exit_code: int
    started_at: datetime
    finished_at: datetime


def build_ssh_connector(
    node: NodeConnectionDTO,
    cipher: CredentialCipher,
    factory: RemoteConnectorFactory,
    *,
    timeout: int | None = None,
) -> RemoteCommandSession:
    """Build an SSH connector from a node connection DTO."""
    kwargs: dict[str, object] = {
        "host": node.host,
        "port": node.port,
        "username": node.username,
        "password": cipher.decrypt(node.password),
        "ssh_key": cipher.decrypt(node.ssh_key),
        "passphrase": cipher.decrypt(node.passphrase),
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return factory.create_ssh(**kwargs)


async def execute_ssh(
    connector: RemoteCommandSession,
    command: str,
) -> SshExecutionResult:
    """Execute a command over SSH and return captured results with timestamps."""
    started_at = datetime.now(UTC)
    async with connector:
        stdout, stderr, exit_code = await connector.execute_command(command)
    finished_at = datetime.now(UTC)
    return SshExecutionResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=finished_at,
    )


async def save_history(
    writer: CommandHistoryWriter,
    *,
    node_id: UUID,
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    started_at: datetime,
    finished_at: datetime,
    command_id: UUID | None = None,
    batch_id: UUID | None = None,
) -> None:
    """Save a command execution record to history."""
    bounded_stdout = bound_output(stdout)
    bounded_stderr = bound_output(stderr)
    await writer.save(
        CommandHistoryCreateDTO(
            node_id=node_id,
            command_id=command_id,
            command_fingerprint=command_fingerprint(command),
            exit_code=exit_code,
            stdout=bounded_stdout.value,
            stderr=bounded_stderr.value,
            stdout_bytes=bounded_stdout.original_bytes,
            stderr_bytes=bounded_stderr.original_bytes,
            truncated=bounded_stdout.truncated or bounded_stderr.truncated,
            batch_id=batch_id,
            started_at=started_at,
            finished_at=finished_at,
        )
    )
