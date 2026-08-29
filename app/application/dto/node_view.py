"""Public-safe node application DTO."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.dto.value_objects import NodeEndpoint
from app.core.types import NodeName, NodeStatus, TagList


@dataclass(frozen=True, slots=True)
class NodeViewDTO:
    """Transport-independent node data without credentials."""

    id: UUID
    name: NodeName
    endpoint: NodeEndpoint
    status: NodeStatus
    username: str | None
    tags: TagList
    created_at: datetime
    updated_at: datetime

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
    def has_docker(self) -> bool:
        return self.endpoint.has_docker
