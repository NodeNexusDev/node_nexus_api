"""Port for managing SSH known_hosts entries."""

from typing import Protocol


class KnownHostsManager(Protocol):
    """Manage OpenSSH known_hosts for host-key verification."""

    async def ensure_host(self, host: str, port: int) -> bool:
        """Ensure host key is present in known_hosts.

        Returns True if a new entry was added, False if already present.
        Raises HostKeyFetchError when the key cannot be fetched/verified.
        """
        ...

    async def refresh_host(self, host: str, port: int) -> bool:
        """Force refresh host key (remove old, fetch new)."""
        ...

    async def ensure_directory(self) -> None:
        """Ensure known_hosts parent directory and file exist."""
        ...
