"""Public-safe node application DTO."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.types import ConnectionType, NodeStatus


@dataclass(frozen=True, slots=True)
class NodeViewDTO:
    """Transport-independent node data without credentials."""

    id: UUID
    name: str
    host: str
    port: int
    connection_type: ConnectionType
    status: NodeStatus
    username: str | None
    docker_host: str | None
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
