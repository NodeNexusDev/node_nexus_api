"""Node connection application DTO."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NodeConnectionDTO:
    """Immutable node data required to open a remote connection."""

    id: UUID
    name: str
    host: str
    port: int
    connection_type: str
    username: str | None
    password: str | None = field(default=None, repr=False)
    ssh_key: str | None = field(default=None, repr=False)
    docker_host: str | None = None
