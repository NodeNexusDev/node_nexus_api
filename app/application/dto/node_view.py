"""Public-safe node application DTO."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NodeViewDTO:
    """Transport-independent node data without credentials."""

    id: UUID
    name: str
    host: str
    port: int
    connection_type: str
    status: str
    username: str | None
    docker_host: str | None
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
