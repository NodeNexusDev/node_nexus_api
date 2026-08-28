"""Node management application DTOs."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.application.dto.node_view import NodeViewDTO
from app.core.types import ConnectionType

NodeUpdateValue = str | int | tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class NodeCreateDTO:
    """Immutable data required to create a node."""

    name: str
    host: str
    port: int
    connection_type: ConnectionType
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    ssh_key: str | None = field(default=None, repr=False)
    passphrase: str | None = field(default=None, repr=False)
    docker_host: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NodeUpdateDTO:
    """Immutable partial node update preserving explicitly provided nulls."""

    changes: tuple[tuple[str, NodeUpdateValue], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class NodeTagDTO:
    """Immutable tag mutation data."""

    tag: str


@dataclass(frozen=True, slots=True)
class NodeListQueryDTO:
    """Immutable offset-based node query."""

    offset: int
    limit: int
    tags: tuple[str, ...] = ()
    search: str | None = None


@dataclass(frozen=True, slots=True)
class NodeCursorQueryDTO:
    """Immutable keyset-based node query."""

    cursor: tuple[datetime, UUID] | None
    limit: int
    tags: tuple[str, ...] = ()
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
