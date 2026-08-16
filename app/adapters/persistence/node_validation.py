"""SSH adapter for validating node credentials without persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.application.dto.node_validation import (
    NodeValidationRequestDTO,
    NodeValidationResultDTO,
)
from app.core.exceptions import ConnectionFailedError

if TYPE_CHECKING:
    from app.application.ports.remote_command import RemoteConnectorFactory

audit = structlog.get_logger("audit")


class SshCredentialValidator:
    """Validate SSH connectivity using the remote connector factory."""

    def __init__(self, connector_factory: RemoteConnectorFactory) -> None:
        self._connector_factory = connector_factory

    async def validate(
        self, request: NodeValidationRequestDTO
    ) -> NodeValidationResultDTO:
        """Attempt an SSH connection with the provided credentials."""
        connector = self._connector_factory.create_ssh(
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            ssh_key=request.ssh_key,
        )

        try:
            async with connector:
                await connector.execute_command("echo ok")
            audit.info(
                "node.validation.ok",
                host=request.host,
                port=request.port,
            )
            return NodeValidationResultDTO(
                status="active",
                message="SSH connection successful",
            )
        except ConnectionFailedError as exc:
            audit.warning(
                "node.validation.failed",
                host=request.host,
                port=request.port,
                error=str(exc),
            )
            return NodeValidationResultDTO(
                status="unreachable",
                message=str(exc),
            )
        except Exception as exc:
            audit.error(
                "node.validation.unexpected_error",
                host=request.host,
                port=request.port,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return NodeValidationResultDTO(
                status="unreachable",
                message=f"Connection failed: {exc}",
            )
