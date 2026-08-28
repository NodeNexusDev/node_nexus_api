"""Transport-independent node credential validation objects."""

from dataclasses import dataclass
from typing import Literal

from app.application.dto.value_objects import NodeCredentials, NodeEndpoint


@dataclass(frozen=True, slots=True)
class NodeValidationRequestDTO:
    """Credentials to validate without saving a node."""

    endpoint: NodeEndpoint
    credentials: NodeCredentials = NodeCredentials()

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


@dataclass(frozen=True, slots=True)
class NodeValidationResultDTO:
    """Result of credential validation."""

    status: Literal["active", "unreachable"] = "unreachable"
    message: str = ""
