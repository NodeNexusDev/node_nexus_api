"""Node management application DTOs."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.core.types import NodeName, Tag, TagList

NodeUpdateValue = str | int | TagList | None


@dataclass(frozen=True, slots=True)
class NodeCreateDTO:
    """Immutable data required to create a node."""

    name: NodeName
    endpoint: NodeEndpoint
    credentials: NodeCredentials = field(default_factory=NodeCredentials)
    tags: TagList = ()

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


@dataclass(frozen=True, slots=True)
class NodeUpdateDTO:
    """Immutable partial node update preserving explicitly provided nulls."""

    changes: tuple[tuple[str, NodeUpdateValue], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class NodeTagDTO:
    """Immutable tag mutation data."""

    tag: Tag


@dataclass(frozen=True, slots=True)
class NodeListQueryDTO:
    """Immutable offset-based node query."""

    offset: int
    limit: int
    tags: TagList = ()
    search: str | None = None


@dataclass(frozen=True, slots=True)
class NodeCursorQueryDTO:
    """Immutable keyset-based node query."""

    cursor: tuple[datetime, UUID] | None
    limit: int
    tags: TagList = ()
    search: str | None = None


@dataclass(frozen=True, slots=True)
class NodePageDTO:
    """Node page returned by a management reader."""

    items: tuple[NodeViewDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class NodeCursorPageDTO:
    """Node keyset page returned by a management reader."""

    items: tuple[NodeViewDTO, ...]
    next_cursor: tuple[datetime, UUID] | None
    has_more: bool
