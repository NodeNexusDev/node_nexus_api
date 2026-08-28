"""Shared application value objects for node aggregates."""

from dataclasses import dataclass, field

from app.core.types import ConnectionType, DockerHost, Host


@dataclass(frozen=True, slots=True)
class NodeCredentials:
    """Immutable credential tuple for a node."""

    username: str | None = None
    password: str | None = field(default=None, repr=False)
    ssh_key: str | None = field(default=None, repr=False)
    passphrase: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class NodeEndpoint:
    """Immutable network endpoint for a node."""

    host: Host
    port: int = 22
    connection_type: ConnectionType = "ssh"
    docker_host: DockerHost | None = None
