"""SSH connector implementation."""

import asyncssh

from app.core.connectors.base import BaseConnector


class SSHConnector(BaseConnector):
    """SSH connector for remote command execution."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        ssh_key: str | None = None,
        timeout: int = 30,
        known_hosts: str | None = None,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._ssh_key = ssh_key
        self._timeout = timeout
        self._known_hosts = known_hosts
        self._connection: asyncssh.SSHClientConnection | None = None

    async def connect(self) -> None:
        """Establish SSH connection.

        Key-based auth is used when ssh_key is provided.
        Password auth is used otherwise.
        """
        kwargs: dict[str, object] = {
            "port": self._port,
            "username": self._username,
            "connect_timeout": self._timeout,
            "known_hosts": self._known_hosts,
        }

        if self._ssh_key:
            kwargs["client_keys"] = [self._ssh_key.encode()]
        elif self._password:
            kwargs["password"] = self._password

        self._connection = await asyncssh.connect(self._host, **kwargs)

    async def disconnect(self) -> None:
        """Close SSH connection."""
        if self._connection:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None

    async def execute_command(self, command: str) -> tuple[str, str, int]:
        """Execute a command on the remote system.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        if not self._connection:
            raise RuntimeError("Not connected")
        result = await self._connection.run(command, timeout=self._timeout)
        return (
            str(result.stdout),
            str(result.stderr),
            result.exit_status or 0,
        )


class SSHConnectorFactory:
    """Factory for creating SSH connectors."""

    def create_ssh(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        ssh_key: str | None,
    ) -> SSHConnector:
        return SSHConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            ssh_key=ssh_key,
        )
