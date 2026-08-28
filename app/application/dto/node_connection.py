"""Node connection application DTO."""

from dataclasses import dataclass
from uuid import UUID

from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.core.types import NodeName


@dataclass(frozen=True, slots=True)
class NodeConnectionDTO:
    """Immutable node data required to open a remote connection."""

    id: UUID
    name: NodeName
    endpoint: NodeEndpoint
    credentials: NodeCredentials

    @property
    def host(self) -> str:
        return self.endpoint.host

    @property
    def port(self) -> int:
        return self.endpoint.port

    @property
    def connection_type(self) -> str:
        return self.endpoint.connection_type

    @property
    def docker_host(self) -> str | None:
        return self.endpoint.docker_host

    @property
    def username(self) -> str | None:
        return self.credentials.username

    @property
    def password(self) -> str | None:
        return self.credentials.password

    @property
    def ssh_key(self) -> str | None:
        return self.credentials.ssh_key

    @property
    def passphrase(self) -> str | None:
        return self.credentials.passphrase
