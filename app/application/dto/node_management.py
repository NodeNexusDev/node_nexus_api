"""Node management application DTOs."""

from dataclasses import dataclass, field

NodeUpdateValue = str | int | tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class NodeCreateDTO:
    """Immutable data required to create a node."""

    name: str
    host: str
    port: int
    connection_type: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    ssh_key: str | None = field(default=None, repr=False)
    docker_host: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NodeUpdateDTO:
    """Immutable partial node update preserving explicitly provided nulls."""

    changes: tuple[tuple[str, NodeUpdateValue], ...]


@dataclass(frozen=True, slots=True)
class NodeTagDTO:
    """Immutable tag mutation data."""

    tag: str
