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
        timeout: int = 30,
        known_hosts: str | None = "",
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._timeout = timeout
        self._known_hosts = known_hosts
        self._connection: asyncssh.SSHClientConnection | None = None

    async def connect(self) -> None:
        """Establish SSH connection."""
        self._connection = await asyncssh.connect(
            self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            connect_timeout=self._timeout,
            known_hosts=self._known_hosts,
        )

    async def disconnect(self) -> None:
        """Close SSH connection."""
        if self._connection:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None

    async def execute_command(self, command: str) -> str:
        """Execute a command on the remote system."""
        if not self._connection:
            raise RuntimeError("Not connected")
        result = await self._connection.run(command, timeout=self._timeout)
        return str(result.stdout)
