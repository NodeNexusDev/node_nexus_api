"""Transport-independent node credential validation objects."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class NodeValidationRequestDTO:
    """Credentials to validate without saving a node."""

    host: str
    port: int = 22
    connection_type: str = "ssh"
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    ssh_key: str | None = field(default=None, repr=False)
    passphrase: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class NodeValidationResultDTO:
    """Result of credential validation."""

    status: Literal["active", "unreachable"] = "unreachable"
    message: str = ""
