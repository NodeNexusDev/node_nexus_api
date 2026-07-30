"""SSH-backed Docker CLI runtime adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.dto.docker import DockerExecResultDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.core.exceptions import ConnectionFailedError

if TYPE_CHECKING:
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.remote_command import RemoteConnectorFactory


class SshDockerRuntime:
    """Execute Docker CLI commands through managed remote sessions."""

    def __init__(
        self,
        connector_factory: RemoteConnectorFactory,
        credential_cipher: CredentialCipher,
    ) -> None:
        self._connector_factory = connector_factory
        self._credential_cipher = credential_cipher

    async def execute(
        self,
        target: NodeConnectionDTO,
        command: str,
        timeout: int = 30,
    ) -> DockerExecResultDTO:
        """Execute Docker CLI arguments on one target."""
        connector = self._connector_factory.create_ssh(
            host=target.host,
            port=target.port,
            username=target.username,
            password=self._credential_cipher.decrypt(target.password),
            ssh_key=self._credential_cipher.decrypt(target.ssh_key),
        )
        try:
            async with connector:
                stdout, stderr, exit_code = await connector.execute_command(command)
            return DockerExecResultDTO(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )
        except Exception as exc:
            raise ConnectionFailedError(
                f"Failed to connect to Docker host {target.host}: {exc}"
            ) from exc
